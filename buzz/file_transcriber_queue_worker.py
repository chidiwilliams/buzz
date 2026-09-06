import json
import logging
import multiprocessing
import os
import queue
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List, Set
from uuid import UUID, uuid4
from dataclasses import dataclass

from buzz.ffmpeg_utils import find_ffmpeg, find_ffprobe
from buzz.pip_utils import subprocess_hide_window_kwargs
from buzz.sleep_inhibitor import TaskActivity

# Fix SSL certificate verification for bundled applications (macOS, Windows)
# This must be done before importing demucs which uses torch.hub with urllib
try:
    import certifi
    os.environ.setdefault('REQUESTS_CA_BUNDLE', certifi.where())
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    os.environ.setdefault('SSL_CERT_DIR', os.path.dirname(certifi.where()))
    # Also update the default SSL context for urllib
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, Qt

# Patch subprocess for demucs to prevent console windows on Windows
if sys.platform == "win32":
    _original_run = subprocess.run
    _original_check_output = subprocess.check_output

    def _patched_run(*args, **kwargs):
        if 'startupinfo' not in kwargs:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = si
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        return _original_run(*args, **kwargs)

    def _patched_check_output(*args, **kwargs):
        if 'startupinfo' not in kwargs:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = si
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        return _original_check_output(*args, **kwargs)

    subprocess.run = _patched_run
    subprocess.check_output = _patched_check_output

from demucs import api as demucsApi

from buzz.locale import _


# Speech extraction runs over the whole file in fixed-length windows. Demucs
# keeps the input and all four separated stems in memory, so separating a whole
# file at once costs about 20x the decoded audio size (~9 GB per hour of audio)
# and grows without bound with file length. Windowing keeps it flat.
_EXTRACTION_WINDOW_SECONDS = 300
# Each window is separated with this much of the neighbouring audio on either
# side, and that context is trimmed off before writing, so window boundaries
# don't show up as seams in the extracted speech.
_EXTRACTION_CONTEXT_SECONDS = 10


def _probe_audio(file_path: str) -> Tuple[bool, float]:
    """Return whether the file has an audio stream and its duration in seconds."""
    result = subprocess.run(
        [
            find_ffprobe(),
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            file_path,
        ],
        capture_output=True,
        **subprocess_hide_window_kwargs(),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed: {result.stderr.decode('utf-8', errors='replace').strip()}"
        )

    probe = json.loads(result.stdout or b"{}")
    audio_streams = [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "audio"
    ]
    if not audio_streams:
        return False, 0.0

    for source in (audio_streams[0], probe.get("format", {})):
        try:
            duration = float(source.get("duration"))
        except (TypeError, ValueError):
            continue
        if duration > 0:
            return True, duration

    return True, 0.0


def _start_audio_decoder(file_path: str, samplerate: int, channels: int, stderr):
    """Decode the file to raw float32 samples streamed on stdout."""
    return subprocess.Popen(
        [
            find_ffmpeg(),
            "-nostdin",
            "-i", file_path,
            "-vn",
            "-f", "f32le",
            "-acodec", "pcm_f32le",
            "-ac", str(channels),
            "-ar", str(samplerate),
            "-loglevel", "error",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=stderr,
        **subprocess_hide_window_kwargs(),
    )


def _start_audio_encoder(speech_path: str, samplerate: int, channels: int, stderr):
    """Encode raw float32 samples read from stdin into ``speech_path``."""
    return subprocess.Popen(
        [
            find_ffmpeg(),
            "-nostdin",
            "-y",
            "-f", "f32le",
            "-ar", str(samplerate),
            "-ac", str(channels),
            "-i", "-",
            "-b:a", "320k",
            "-loglevel", "error",
            speech_path,
        ],
        stdin=subprocess.PIPE,
        stderr=stderr,
        **subprocess_hide_window_kwargs(),
    )


def _read_log(log_file) -> str:
    """Read back what ffmpeg wrote to its stderr file."""
    try:
        log_file.seek(0)
        return log_file.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def _read_frames(stream, frames: int, channels: int):
    """Read up to ``frames`` frames of float32 audio as a ``(channels, n)`` array."""
    import numpy as np

    data = stream.read(frames * channels * 4)
    if not data:
        return np.zeros((channels, 0), dtype=np.float32)
    # A truncated final read would misalign the channel interleaving.
    usable = len(data) - (len(data) % (channels * 4))
    samples = np.frombuffer(data[:usable], dtype=np.float32)
    return samples.reshape(-1, channels).T.copy()


def _remove_partial_speech_file(speech_path: str) -> None:
    """Drop a half-written speech file so nothing downstream picks it up."""
    try:
        os.remove(speech_path)
    except OSError:
        pass


def _extract_speech_streaming(conn, file_path: str, speech_path: str, device: str) -> None:
    """Separate vocals window by window, writing them out as we go."""
    import numpy as np
    import torch

    has_audio, duration = _probe_audio(file_path)
    if not has_audio:
        conn.send(("no_audio", file_path))
        return

    # Window start offset of the separation currently running, so the demucs
    # per-segment callback can be reported as a position in the whole file.
    window_offset = 0

    def callback(progress):
        try:
            conn.send(
                (
                    "progress",
                    window_offset + progress["segment_offset"],
                    total_frames,
                )
            )
        except Exception:
            pass

    separator = demucsApi.Separator(
        device=device,
        progress=False,
        callback=callback,
    )
    samplerate = separator.samplerate
    channels = separator.audio_channels
    total_frames = int(duration * samplerate)

    window_frames = _EXTRACTION_WINDOW_SECONDS * samplerate
    context_frames = _EXTRACTION_CONTEXT_SECONDS * samplerate

    # ffmpeg's stderr goes to temporary files rather than pipes; nothing reads
    # the pipes while separation runs, and a chatty decode could fill them and
    # deadlock ffmpeg.
    decoder_log = tempfile.TemporaryFile()
    encoder_log = tempfile.TemporaryFile()
    decoder = _start_audio_decoder(file_path, samplerate, channels, decoder_log)
    encoder = _start_audio_encoder(speech_path, samplerate, channels, encoder_log)
    wrote_any = False

    try:
        buffer = np.zeros((channels, 0), dtype=np.float32)
        buffer_start = 0  # frame offset of buffer[0] in the whole file
        written = 0  # frames already handed to the encoder
        at_end = False

        while not at_end:
            chunk = _read_frames(decoder.stdout, window_frames, channels)
            at_end = chunk.shape[1] == 0
            buffer = np.concatenate((buffer, chunk), axis=1)
            buffer_end = buffer_start + buffer.shape[1]

            # Everything but the last window keeps its trailing context back so
            # the next window can separate it with audio on both sides.
            write_end = buffer_end if at_end else buffer_end - context_frames
            if write_end <= written:
                continue

            window_offset = buffer_start
            _origin, separated = separator.separate_tensor(
                torch.from_numpy(buffer.copy()), samplerate
            )
            vocals = separated["vocals"]
            del separated, _origin

            segment = vocals[:, written - buffer_start: write_end - buffer_start]
            segment = segment.clamp(-1.0, 1.0).t().contiguous().numpy()
            encoder.stdin.write(segment.astype(np.float32).tobytes())
            wrote_any = wrote_any or segment.shape[0] > 0
            written = write_end
            del vocals, segment

            keep_from = max(buffer_start, written - context_frames)
            buffer = buffer[:, keep_from - buffer_start:].copy()
            buffer_start = keep_from

        decoder.stdout.close()
        decoder_error = _read_log(decoder_log)
        if decoder.wait() != 0:
            raise RuntimeError(f"ffmpeg failed to decode audio: {decoder_error}")
    finally:
        if decoder.poll() is None:
            decoder.kill()
        try:
            encoder.stdin.close()
        except OSError:
            pass
        encoder_error = _read_log(encoder_log)
        encoder_returncode = encoder.wait()
        decoder_log.close()
        encoder_log.close()

    if not wrote_any:
        # The container advertised an audio stream but decoded to nothing.
        _remove_partial_speech_file(speech_path)
        conn.send(("no_audio", file_path))
        return

    if encoder_returncode != 0:
        _remove_partial_speech_file(speech_path)
        raise RuntimeError(f"ffmpeg failed to write extracted speech: {encoder_error}")

    conn.send(("done", None))


def _speech_extraction_worker(conn, file_path: str, speech_path: str, device: str) -> None:
    """Extract speech with demucs in a dedicated process.
    """
    try:
        _extract_speech_streaming(conn, file_path, speech_path, device)
    except Exception as e:
        logging.error(f"Error during speech extraction: {e}", exc_info=True)
        _remove_partial_speech_file(speech_path)
        conn.send(("error", str(e)))
    finally:
        try:
            conn.close()
        except Exception:
            pass


from buzz.model_loader import ModelType
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.openai_whisper_api_file_transcriber import (
    OpenAIWhisperAPIFileTranscriber,
)
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment
from buzz.transcriber.whisper_file_transcriber import WhisperFileTranscriber


@dataclass
class _CurrentTranscription:
    task: Optional[FileTranscriptionTask] = None
    activity_token: Optional[UUID] = None
    transcriber: Optional[FileTranscriber] = None
    transcriber_thread: Optional[QThread] = None


@dataclass(frozen=True)
class _QueuedTranscription:
    task: FileTranscriptionTask
    activity_token: UUID


class FileTranscriberQueueWorker(QObject):
    tasks_queue: multiprocessing.Queue

    task_started = pyqtSignal(FileTranscriptionTask)
    task_progress = pyqtSignal(FileTranscriptionTask, float)
    task_download_progress = pyqtSignal(FileTranscriptionTask, float)
    task_completed = pyqtSignal(FileTranscriptionTask, list)
    task_error = pyqtSignal(FileTranscriptionTask, str)
    queue_busy_changed = pyqtSignal(bool)

    completed = pyqtSignal()
    trigger_run = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.tasks_queue = queue.Queue()
        self.current = _CurrentTranscription()
        self.canceled_tasks: Set[UUID] = set()
        self.speech_path = None
        self.speech_extractor_process = None
        self.is_running = False
        self.task_activity = TaskActivity(self.queue_busy_changed.emit)
        # Assigned by MainWindow after construction. Duck-typed to avoid an
        # import cycle with the plugins package.
        self.plugin_manager = None
        # Use QueuedConnection to ensure run() is called in the correct thread context
        # and doesn't block signal handlers
        self.trigger_run.connect(self.run, Qt.ConnectionType.QueuedConnection)

    @pyqtSlot()
    def run(self):
        if self.is_running:
            return

        logging.debug("Waiting for next transcription task")

        self._cleanup_previous_transcriber()

        if not self._get_next_task():
            self.is_running = False
            self.completed.emit()
            return

        self.is_running = True

        if self.current.task.transcription_options.extract_speech:
            status = self._setup_speech_extraction()
            if status == "error":
                self.is_running = False
                self._on_task_finished()
                return

        if not self._run_plugins():
            return

        logging.debug("Starting next transcription task")
        self.task_progress.emit(self.current.task, 0)

        self._create_transcriber()
        self._setup_transcriber_thread()

    def _cleanup_previous_transcriber(self):
        if self.current.transcriber is not None:
            self.current.transcriber.stop()
            self.current.transcriber = None

    def _get_next_task(self) -> bool:
        while True:
            queued = self.tasks_queue.get()
            if queued is None:
                return False
            if isinstance(queued, _QueuedTranscription):
                self.current.task = queued.task
                self.current.activity_token = queued.activity_token
            else:
                self.current.task = queued
                self.current.activity_token = None
            if self.current.task.uid in self.canceled_tasks:
                if self.current.activity_token is not None:
                    self.task_activity.finish(self.current.activity_token)
                continue
            return True

    def _setup_speech_extraction(self) -> str:
        logging.debug("Will extract speech")

        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false").lower() == "true"
        if force_cpu:
            device = "cpu"
        else:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

        task_file_path = Path(self.current.task.file_path)
        speech_path = task_file_path.with_name(f"{task_file_path.stem}_speech.mp3")

        status = self._extract_speech(str(task_file_path), str(speech_path), device)

        if status == "error":
            self.task_error.emit(
                self.current.task,
                _("Speech extraction failed! Check your internet connection \u2014 a model may need to be downloaded."),
            )
        elif status == "ok":
            self.speech_path = speech_path
            if not self.current.task.original_file_path:
                self.current.task.original_file_path = str(task_file_path)
            self.current.task.file_path = str(speech_path)

        return status

    def _run_plugins(self) -> bool:
        """Run before_transcription and check_skip hooks.

        Returns False if a plugin signaled that the task should be skipped,
        True to continue with normal transcription.
        """
        if self.plugin_manager is not None:
            try:
                self.plugin_manager.run_before_transcription(self.current.task)
            except Exception as e:
                logging.error(f"Plugin before_transcription failed: {e}", exc_info=True)

            should_skip, skip_segments = self.plugin_manager.run_check_skip(self.current.task)
            if should_skip:
                logging.debug("Skipping transcription task (plugin signaled skip)")
                self.current.task.status = FileTranscriptionTask.Status.SKIPPED
                self.on_task_completed(skip_segments)
                self.is_running = False
                self._on_task_finished()
                return False

        return True

    def _create_transcriber(self):
        model_type = self.current.task.transcription_options.model.model_type
        if model_type == ModelType.OPEN_AI_WHISPER_API:
            self.current.transcriber = OpenAIWhisperAPIFileTranscriber(
                task=self.current.task
            )
        elif (
            model_type == ModelType.WHISPER_CPP
            or model_type == ModelType.HUGGING_FACE
            or model_type == ModelType.WHISPER
            or model_type == ModelType.FASTER_WHISPER
        ):
            self.current.transcriber = WhisperFileTranscriber(task=self.current.task)
        else:
            raise Exception(f"Unknown model type: {model_type}")

    def _setup_transcriber_thread(self):
        self.current.transcriber_thread = QThread(self)

        self.current.transcriber.moveToThread(self.current.transcriber_thread)

        self.current.transcriber_thread.started.connect(self.current.transcriber.run)
        self.current.transcriber.completed.connect(self.current.transcriber_thread.quit)
        self.current.transcriber.error.connect(self.current.transcriber_thread.quit)

        self.current.transcriber.completed.connect(self.current.transcriber.deleteLater)
        self.current.transcriber.error.connect(self.current.transcriber.deleteLater)
        self.current.transcriber_thread.finished.connect(
            self.current.transcriber_thread.deleteLater
        )

        self.current.transcriber.progress.connect(self.on_task_progress)
        self.current.transcriber.download_progress.connect(
            self.on_task_download_progress
        )
        self.current.transcriber.error.connect(self.on_task_error)

        self.current.transcriber.completed.connect(self.on_task_completed)

        task = self.current.task
        activity_token = self.current.activity_token
        self.current.transcriber.error.connect(
            lambda: self._on_task_finished(task, activity_token)
        )
        self.current.transcriber.completed.connect(
            lambda: self._on_task_finished(task, activity_token)
        )

        self.task_started.emit(self.current.task)
        self.current.transcriber_thread.start()

    def _extract_speech(self, file_path: str, speech_path: str, device: str) -> str:
        """Run demucs speech extraction in a separate process.

        Returns one of ``"ok"``, ``"no_audio"`` or ``"error"``.
        """
        recv_conn, send_conn = multiprocessing.Pipe(duplex=False)
        process = multiprocessing.Process(
            target=_speech_extraction_worker,
            args=(send_conn, file_path, speech_path, device),
        )
        self.speech_extractor_process = process
        process.start()
        # The parent only reads; close its copy of the send end so recv() gets
        # EOF once the child exits.
        send_conn.close()

        status = None
        error_detail = None
        try:
            while True:
                try:
                    message = recv_conn.recv()
                except EOFError:
                    break

                kind = message[0]
                if kind == "progress":
                    audio_length = int(message[2] * 100)
                    if audio_length:
                        self.task_progress.emit(
                            self.current.task,
                            int(message[1] * 100) / audio_length,
                        )
                elif kind == "done":
                    status = "ok"
                elif kind == "no_audio":
                    status = "no_audio"
                    logging.warning(
                        f"Skipping speech extraction, file has no audio stream: {message[1]}"
                    )
                elif kind == "error":
                    status = "error"
                    error_detail = message[1]
        finally:
            try:
                recv_conn.close()
            except OSError:
                pass
            process.join()
            self.speech_extractor_process = None

        if status is None:
            # Child died without reporting a terminal result (e.g. killed).
            status = "error"
            error_detail = (
                f"speech extraction process exited with code {process.exitcode}"
            )

        if status == "error":
            logging.error(f"Error during speech extraction: {error_detail}")

        return status

    def _terminate_speech_extractor_process(self):
        """Terminate the speech extraction process if one is still running."""
        process = self.speech_extractor_process
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                logging.warning(
                    "Speech extraction process did not terminate gracefully, killing it"
                )
                process.kill()
                process.join(timeout=5)

    def _on_task_finished(
        self,
        task: Optional[FileTranscriptionTask] = None,
        activity_token: Optional[UUID] = None,
    ):
        """Called when a task completes or errors, resets state and triggers next run"""
        if task is None:
            task = self.current.task
            activity_token = self.current.activity_token
        if activity_token is not None:
            self.task_activity.finish(activity_token)
        if task is not self.current.task or activity_token != self.current.activity_token:
            return
        self.current.activity_token = None
        self.is_running = False
        # Use signal to avoid blocking in signal handler context
        self.trigger_run.emit()

    def add_task(self, task: FileTranscriptionTask):
        # Remove from canceled tasks if it was previously canceled (for restart functionality)
        if task.uid in self.canceled_tasks:
            self.canceled_tasks.remove(task.uid)

        activity_token = uuid4()
        self.task_activity.add(activity_token)
        self.tasks_queue.put(_QueuedTranscription(task, activity_token))
        # If the worker is not currently running, trigger it to start processing
        # Use signal to avoid blocking the main thread
        if not self.is_running:
            self.trigger_run.emit()

    def cancel_task(self, task_id: UUID):
        self.canceled_tasks.add(task_id)

        if self.current.task is not None and self.current.task.uid == task_id:
            task = self.current.task
            activity_token = self.current.activity_token
            transcriber = self.current.transcriber
            transcriber_thread = self.current.transcriber_thread
            self._terminate_speech_extractor_process()

            if transcriber is not None:
                transcriber.stop()

            if transcriber_thread is not None:
                if not transcriber_thread.wait(5000):
                    logging.warning("Transcriber thread did not terminate gracefully")
                    transcriber_thread.terminate()
                    transcriber_thread.wait()
                    self._on_task_finished(task, activity_token)

    def on_task_error(self, error: str):
        if (
            self.current.task is not None
            and self.current.task.uid not in self.canceled_tasks
        ):
            # Check if the error indicates cancellation
            if "canceled" in error.lower() or "cancelled" in error.lower():
                self.current.task.status = FileTranscriptionTask.Status.CANCELED
                self.current.task.error = error
            else:
                self.current.task.status = FileTranscriptionTask.Status.FAILED
                self.current.task.error = error
            self.task_error.emit(self.current.task, error)

    @pyqtSlot(tuple)
    def on_task_progress(self, progress: Tuple[int, int]):
        if self.current.task is not None:
            self.task_progress.emit(self.current.task, progress[0] / progress[1])

    def on_task_download_progress(self, fraction_downloaded: float):
        if self.current.task is not None:
            self.task_download_progress.emit(self.current.task, fraction_downloaded)

    @pyqtSlot(list)
    def on_task_completed(self, segments: List[Segment]):
        if self.current.task is not None:
            self.task_completed.emit(self.current.task, segments)

        if self.speech_path is not None:
            try:
                Path(self.speech_path).unlink()
            except Exception:
                pass
            self.speech_path = None

    def stop(self):
        self.task_activity.clear()
        self.tasks_queue.put(None)
        if self.current.transcriber is not None:
            self.current.transcriber.stop()

        # Terminate the speech extraction process if one is still running.
        self._terminate_speech_extractor_process()
