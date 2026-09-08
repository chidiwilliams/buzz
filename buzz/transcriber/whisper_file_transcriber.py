import datetime
import json
import logging
import multiprocessing
import re
import os
import sys
from dataclasses import dataclass

# Preload CUDA libraries before importing torch - required for subprocess contexts
from buzz import cuda_setup  # noqa: F401

import torch
import platform
from platformdirs import user_cache_dir
from multiprocessing.connection import Connection, wait
from threading import Condition, Event, RLock, Thread
from typing import Optional, List

import psutil
from PyQt6.QtCore import QObject, QThread, pyqtSlot

from buzz import whisper_audio
from buzz.conn import pipe_stderr
from buzz.model_loader import ModelType, map_language_to_mms
from buzz.transformers_whisper import TransformersTranscriber
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.transcriber import (
    FileTranscriptionTask,
    Segment,
    Task,
    DEFAULT_WHISPER_TEMPERATURE,
)
from buzz.transcriber.whisper_cpp import WhisperCpp

import av
import faster_whisper
import whisper
import stable_whisper
from stable_whisper import WhisperResult

PROGRESS_REGEX = re.compile(r"\d+(\.\d+)?%")


@dataclass(frozen=True, slots=True)
class DetailedTranscriptionWord:
    """One backend-native timed word linked to its phrase segment."""

    source_segment_ordinal: int
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class DetailedTranscriptionResult:
    """Backend-native phrase segments and words from one inference."""

    segments: tuple[Segment, ...]
    words: tuple[DetailedTranscriptionWord, ...]


def terminate_child_processes(pid: int, timeout: float = 5.0) -> None:
    """Terminate every descendant process of ``pid`` (but not ``pid`` itself).

    For whisper.cpp the actual work runs in a ``whisper-cli`` subprocess spawned
    by our multiprocessing worker. ``multiprocessing.Process.terminate()`` only
    signals the worker, leaving that CLI orphaned and still consuming CPU/GPU
    after the user presses Stop or closes the app. This kills those descendants.

    Crucially it does *not* touch ``pid`` itself: the worker is a direct child
    of the app process and must be reaped via ``multiprocessing`` (join). Calling
    ``psutil.wait_procs`` on it here would steal the ``waitpid`` reap and leave
    ``Process.is_alive()`` stuck reporting True. The descendants are grandchildren
    of the app, so psutil only polls them and no such race occurs.
    """
    try:
        parent = psutil.Process(pid)
    except (psutil.NoSuchProcess, ValueError):
        return

    # Snapshot the tree before anything gets reparented by the worker exiting.
    try:
        descendants = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return

    # Ask each descendant to exit (SIGTERM / TerminateProcess).
    for proc in descendants:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _, alive = psutil.wait_procs(descendants, timeout=timeout)

    # Force-kill whatever ignored the polite request.
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, alive = psutil.wait_procs(alive, timeout=timeout)
    if alive:
        raise RuntimeError("Transcription child processes did not terminate")


def check_file_has_audio_stream(file_path: str) -> None:
    """Check if a media file has at least one audio stream.

    Raises:
        ValueError: If the file has no audio streams.
    """
    try:
        with av.open(file_path) as container:
            if len(container.streams.audio) == 0:
                raise ValueError("No audio streams found")
    except av.error.InvalidDataError as e:
        raise ValueError(f"Invalid media file: {e}")
    except (av.error.FileNotFoundError, OSError, UnicodeDecodeError):
        raise ValueError("File not found")


class WhisperFileTranscriber(FileTranscriber):
    """WhisperFileTranscriber transcribes an audio file to text, writes the text to a file, and then opens the file
    using the default program for opening txt files."""

    current_process: multiprocessing.Process
    running = False
    read_line_thread: Optional[Thread] = None
    READ_LINE_THREAD_STOP_TOKEN = "--STOP--"

    def __init__(
        self, task: FileTranscriptionTask, parent: Optional["QObject"] = None
    ) -> None:
        super().__init__(task, parent)
        self.segments = []
        self.started_process = False
        self.stopped = False
        self._lifecycle_lock = RLock()
        self._cleanup_condition = Condition(self._lifecycle_lock)
        self._cleanup_claimed = False
        # Success only; the condition also wakes finalization after a failure.
        self._cleanup_done = Event()
        self._cleanup_error = None
        self._transcription_entered = False
        self.recv_pipe = None
        self.send_pipe = None
        self.error_message = None
        self.detailed_words: list[DetailedTranscriptionWord] = []

    def transcribe(self) -> List[Segment]:
        time_started = datetime.datetime.now()
        logging.debug(
            "Starting whisper file transcription, task = %s", self.transcription_task
        )

        if torch.cuda.is_available():
            logging.debug(f"CUDA version detected: {torch.version.cuda}")

        with self._lifecycle_lock:
            if self.stopped:
                raise Exception("Transcription was canceled")
            self._transcription_entered = True
            self._cleanup_claimed = False
            self._cleanup_done.clear()
            self._cleanup_error = None

        try:
            recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)
            with self._lifecycle_lock:
                self.recv_pipe, self.send_pipe = recv_pipe, send_pipe
            process = multiprocessing.Process(
                target=self.transcribe_whisper,
                args=(send_pipe, self.transcription_task),
            )
            with self._lifecycle_lock:
                self.current_process = process

            # Do not hold the lock across spawn: stop() must be able to record
            # a cancellation while Process.start() is still in progress.
            process.start()
            with self._lifecycle_lock:
                self.started_process = True
                pending_stop = self.stopped
                if not pending_stop:
                    # Publish/start the reader before stop() can claim its pipe.
                    self.read_line_thread = Thread(
                        target=self.read_line, args=(recv_pipe,)
                    )
                    self.read_line_thread.start()

            if pending_stop:
                self.stop()
                raise Exception("Transcription was canceled")

            # Wait without reaping; only the cleanup owner calls join(). This
            # also lets a concurrent stop() terminate and reap the worker once.
            wait([process.sentinel])
        except Exception:
            self.stop()
            raise
        finally:
            self._cleanup_transcription(cancel=self.stopped)
            # A concurrent stop() may own cleanup. Do not finish the Qt worker
            # (or consume its reader's result) until that owner has finished.
            with self._cleanup_condition:
                self._cleanup_condition.wait_for(lambda: not self._cleanup_claimed)
                if self._cleanup_error is not None:
                    raise self._cleanup_error

        logging.debug(
            "whisper process completed with code = %s, time taken = %s,"
            " number of segments = %s",
            self.current_process.exitcode,
            datetime.datetime.now() - time_started,
            len(self.segments),
        )

        if self.current_process.exitcode != 0:
            # Check if the process was terminated (likely due to cancellation)
            # Exit codes 124-128 are often used for termination signals
            if self.current_process.exitcode in [
                124,
                125,
                126,
                127,
                128,
                130,
                137,
                143,
            ]:
                # Process was likely terminated, treat as cancellation
                logging.debug(
                    "Whisper process was terminated (exit code: %s), treating as cancellation",
                    self.current_process.exitcode,
                )
                raise Exception("Transcription was canceled")
            else:
                error = self.error_message or "Unknown error"
                logging.error(
                    "Whisper process failed (exit code: %s): %s",
                    self.current_process.exitcode,
                    error,
                )
                raise Exception(error)

        return self.segments

    def _cleanup_transcription(self, *, cancel: bool) -> None:
        with self._lifecycle_lock:
            if self._cleanup_claimed or self._cleanup_done.is_set():
                return
            self._cleanup_claimed = True
            self._cleanup_done.clear()
            process = self.current_process if self.started_process else None
            recv_pipe, send_pipe = self.recv_pipe, self.send_pipe
            reader = self.read_line_thread

        reaped = process is None
        cleanup_error = None
        try:
            try:
                if process is not None:
                    if cancel:
                        if process.pid is not None:
                            terminate_child_processes(process.pid)
                        process.terminate()
                    process.join(timeout=10 if cancel else None)
                    if cancel and process.is_alive():
                        logging.warning("Process didn't terminate gracefully, force killing")
                        process.kill()
                        process.join(timeout=5)
                    reaped = not process.is_alive()
                    if not reaped:
                        raise RuntimeError("Transcription process did not terminate")
            finally:
                self._close_transcription_resources(
                    recv_pipe, send_pipe, reader, reader_timeout=5 if cancel else 3
                )
        except BaseException as exc:
            cleanup_error = exc
            raise
        finally:
            with self._cleanup_condition:
                if reaped:
                    self.started_process = False
                # Keep the resource references on failure; the next owner skips
                # the already-reaped process and retries only pending resources.
                self._cleanup_error = cleanup_error
                self._cleanup_claimed = False
                if cleanup_error is None:
                    self._cleanup_done.set()
                self._cleanup_condition.notify_all()

    @staticmethod
    def _close_transcription_resources(
        recv_pipe, send_pipe, reader, *, reader_timeout: float
    ) -> None:
        """Close/join the owner's resource snapshot without a lifecycle lock."""
        # Close the send pipe after process ends to signal read_line thread to stop
        # This prevents the read thread from blocking on recv() after the process is gone
        try:
            if send_pipe and not send_pipe.closed:
                send_pipe.close()
        except OSError:
            pass

        # Close the receive pipe to unblock the read_line thread
        try:
            if recv_pipe and not recv_pipe.closed:
                recv_pipe.close()
        except OSError:
            pass

        # Join read_line_thread with timeout to prevent hanging
        if reader and reader.is_alive():
            reader.join(timeout=reader_timeout)
            if reader.is_alive():
                logging.warning(
                    "Read line thread didn't terminate gracefully"
                )

        if any(pipe and not pipe.closed for pipe in (recv_pipe, send_pipe)) or (
            reader and reader.is_alive()
        ):
            raise RuntimeError("Transcription resources did not close")

    @classmethod
    def transcribe_whisper(
        cls, stderr_conn: Connection, task: FileTranscriptionTask
    ) -> None:
        cls._transcribe_whisper_worker(stderr_conn, task, detailed=False)

    @classmethod
    def _transcribe_whisper_worker(
        cls,
        stderr_conn: Connection,
        task: FileTranscriptionTask,
        *,
        detailed: bool,
    ) -> None:
        # Patch subprocess on Windows to prevent console window flash
        # This is needed because multiprocessing spawns a new process without the main process patches
        if sys.platform == "win32":
            import subprocess

            _original_run = subprocess.run
            _original_popen = subprocess.Popen

            def _patched_run(*args, **kwargs):
                if "startupinfo" not in kwargs:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = subprocess.SW_HIDE
                    kwargs["startupinfo"] = si
                if "creationflags" not in kwargs:
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                return _original_run(*args, **kwargs)

            class _PatchedPopen(subprocess.Popen):
                def __init__(self, *args, **kwargs):
                    if "startupinfo" not in kwargs:
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        si.wShowWindow = subprocess.SW_HIDE
                        kwargs["startupinfo"] = si
                    if "creationflags" not in kwargs:
                        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                    super().__init__(*args, **kwargs)

            subprocess.run = _patched_run
            subprocess.Popen = _PatchedPopen

        try:
            # Check if the file has audio streams before processing
            check_file_has_audio_stream(task.file_path)

            with pipe_stderr(stderr_conn):
                model_type = task.transcription_options.model.model_type
                if detailed and model_type == ModelType.FASTER_WHISPER:
                    detailed_result = cls.transcribe_faster_whisper_detailed(task)
                elif detailed and model_type == ModelType.WHISPER:
                    detailed_result = cls.transcribe_openai_whisper_detailed(task)
                elif detailed:
                    raise Exception(
                        f"Detailed transcription does not support model type: {model_type}"
                    )
                elif model_type == ModelType.WHISPER_CPP:
                    segments = cls.transcribe_whisper_cpp(task)
                elif model_type == ModelType.HUGGING_FACE:
                    sys.stderr.write("0%\n")
                    segments = cls.transcribe_hugging_face(task)
                    sys.stderr.write("100%\n")
                elif model_type == ModelType.FASTER_WHISPER:
                    segments = cls.transcribe_faster_whisper(task)
                elif model_type == ModelType.WHISPER:
                    segments = cls.transcribe_openai_whisper(task)
                else:
                    raise Exception(f"Invalid model type: {model_type}")

                if detailed:
                    detailed_json = json.dumps(
                        {
                            "segments": [
                                {
                                    "start": segment.start,
                                    "end": segment.end,
                                    "text": segment.text,
                                }
                                for segment in detailed_result.segments
                            ],
                            "words": [
                                {
                                    "source_segment_ordinal": word.source_segment_ordinal,
                                    "start_ms": word.start_ms,
                                    "end_ms": word.end_ms,
                                    "text": word.text,
                                }
                                for word in detailed_result.words
                            ],
                        },
                        ensure_ascii=True,
                    )
                    sys.stderr.write(f"detailed_result = {detailed_json}\n")
                else:
                    segments_json = json.dumps(
                        segments, ensure_ascii=True, default=vars
                    )
                    sys.stderr.write(f"segments = {segments_json}\n")
                sys.stderr.write(
                    WhisperFileTranscriber.READ_LINE_THREAD_STOP_TOKEN + "\n"
                )
        except Exception as e:
            # Send error message back to the parent process
            stderr_conn.send(f"error = {str(e)}\n")
            stderr_conn.send(WhisperFileTranscriber.READ_LINE_THREAD_STOP_TOKEN + "\n")
            raise

    @classmethod
    def transcribe_whisper_cpp(cls, task: FileTranscriptionTask) -> List[Segment]:
        return WhisperCpp.transcribe(task)

    @classmethod
    def transcribe_hugging_face(cls, task: FileTranscriptionTask) -> List[Segment]:
        if not task.model_path:
            raise FileNotFoundError(
                "Hugging Face model is not available locally. "
                "The model download did not complete, try downloading it again."
            )

        model = TransformersTranscriber(task.model_path)

        # Handle language - MMS uses ISO 639-3 codes, Whisper uses ISO 639-1
        if model.is_mms_model:
            language = map_language_to_mms(task.transcription_options.language or "eng")
            # MMS only supports transcription, ignore translation task
            effective_task = Task.TRANSCRIBE.value
            # MMS doesn't support word-level timestamps
            word_timestamps = False
        else:
            language = (
                task.transcription_options.language
                if task.transcription_options.language is not None
                else "en"
            )
            effective_task = task.transcription_options.task.value
            word_timestamps = task.transcription_options.word_level_timings

        initial_prompt = (
            ""
            if model.is_mms_model
            else (task.transcription_options.initial_prompt or "")
        )
        result = model.transcribe(
            audio=task.file_path,
            language=language,
            task=effective_task,
            word_timestamps=word_timestamps,
            initial_prompt=initial_prompt,
        )
        return [
            Segment(
                start=int(segment.get("start") * 1000),
                end=int(segment.get("end") * 1000),
                text=segment.get("text"),
                translation="",
            )
            for segment in result.get("segments")
        ]

    @classmethod
    def transcribe_faster_whisper(cls, task: FileTranscriptionTask) -> List[Segment]:
        whisper_segments = cls._run_faster_whisper(task, detailed=False)
        segments = []
        for segment in whisper_segments:
            # Segment will contain words if word-level timings is True
            if segment.words:
                for word in segment.words:
                    segments.append(
                        Segment(
                            start=int(word.start * 1000),
                            end=int(word.end * 1000),
                            text=word.word,
                            translation="",
                        )
                    )
            else:
                segments.append(
                    Segment(
                        start=int(segment.start * 1000),
                        end=int(segment.end * 1000),
                        text=segment.text,
                        translation="",
                    )
                )

        return segments

    @classmethod
    def transcribe_faster_whisper_detailed(
        cls, task: FileTranscriptionTask
    ) -> DetailedTranscriptionResult:
        whisper_segments = cls._run_faster_whisper(task, detailed=True)
        segments: list[Segment] = []
        words: list[DetailedTranscriptionWord] = []
        for segment_ordinal, segment in enumerate(whisper_segments):
            segments.append(
                Segment(
                    start=int(segment.start * 1000),
                    end=int(segment.end * 1000),
                    text=segment.text,
                    translation="",
                )
            )
            for word in segment.words or ():
                text = word.word.strip()
                if not text:
                    continue
                words.append(
                    DetailedTranscriptionWord(
                        source_segment_ordinal=segment_ordinal,
                        start_ms=int(word.start * 1000),
                        end_ms=int(word.end * 1000),
                        text=text,
                    )
                )
        return DetailedTranscriptionResult(tuple(segments), tuple(words))

    @classmethod
    def _run_faster_whisper(cls, task: FileTranscriptionTask, *, detailed: bool):
        # Use the already-resolved local model path so we never hit the network
        model_size_or_path = task.model_path
        if not model_size_or_path:
            raise FileNotFoundError(
                "Faster Whisper model is not available locally. "
                "Check BUZZ_MODEL_ROOT and download the model into that cache first."
            )
            return []

        model_root_dir = user_cache_dir("Buzz")
        model_root_dir = os.path.join(model_root_dir, "models")
        model_root_dir = os.getenv("BUZZ_MODEL_ROOT", model_root_dir)
        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        if force_cpu != "false":
            os.environ["CUDA_VISIBLE_DEVICES"] = ""

        device = "auto"
        if torch.cuda.is_available() and torch.version.cuda < "12":
            logging.debug("Unsupported CUDA version (<12), using CPU")
            device = "cpu"

        if not torch.cuda.is_available():
            logging.debug("CUDA is not available, using CPU")
            device = "cpu"

        if force_cpu != "false":
            device = "cpu"

        # Check if user wants reduced GPU memory usage (int8 quantization)
        reduce_gpu_memory = os.getenv("BUZZ_REDUCE_GPU_MEMORY", "false") != "false"
        compute_type = "default"
        if reduce_gpu_memory:
            compute_type = "int8" if device == "cpu" else "int8_float16"
            logging.debug(f"Using {compute_type} compute type for reduced memory usage")

        model = faster_whisper.WhisperModel(
            model_size_or_path=model_size_or_path,
            download_root=model_root_dir,
            device=device,
            compute_type=compute_type,
            cpu_threads=(os.cpu_count() or 8) // 2,
        )

        audio = whisper_audio.load_audio(task.file_path)

        batched_model = faster_whisper.BatchedInferencePipeline(model=model)
        common_options = {
            "audio": audio,
            "language": task.transcription_options.language,
            "task": task.transcription_options.task.value,
            "initial_prompt": task.transcription_options.initial_prompt,
            "no_speech_threshold": 0.4,
            "log_progress": True,
        }
        if detailed:
            whisper_segments, _ = batched_model.transcribe(
                **common_options,
                temperature=0.0,
                beam_size=5,
                best_of=5,
                patience=1.0,
                word_timestamps=True,
            )
        else:
            whisper_segments, _ = batched_model.transcribe(
                **common_options,
                # Prevent crash on Windows https://github.com/SYSTRAN/faster-whisper/issues/71#issuecomment-1526263764
                temperature=0
                if platform.system() == "Windows"
                else DEFAULT_WHISPER_TEMPERATURE,
                word_timestamps=task.transcription_options.word_level_timings,
            )
        return whisper_segments

    @classmethod
    def transcribe_openai_whisper(cls, task: FileTranscriptionTask) -> List[Segment]:
        model = cls._load_openai_whisper_model(task)

        if task.transcription_options.word_level_timings:
            stable_whisper.modify_model(model)
            result: WhisperResult = model.transcribe(
                audio=whisper_audio.load_audio(task.file_path),
                language=task.transcription_options.language,
                task=task.transcription_options.task.value,
                temperature=DEFAULT_WHISPER_TEMPERATURE,
                initial_prompt=task.transcription_options.initial_prompt,
                no_speech_threshold=0.4,
                fp16=False,
            )
            return [
                Segment(
                    start=int(word.start * 1000),
                    end=int(word.end * 1000),
                    text=word.word.strip(),
                    translation="",
                )
                for segment in result.segments
                for word in segment.words
            ]

        result: dict = model.transcribe(
            audio=whisper_audio.load_audio(task.file_path),
            language=task.transcription_options.language,
            task=task.transcription_options.task.value,
            temperature=task.transcription_options.temperature,
            initial_prompt=task.transcription_options.initial_prompt,
            verbose=False,
            fp16=False,
        )
        segments = result.get("segments")
        return [
            Segment(
                start=int(segment.get("start") * 1000),
                end=int(segment.get("end") * 1000),
                text=segment.get("text"),
                translation="",
            )
            for segment in segments
        ]

    @classmethod
    def transcribe_openai_whisper_detailed(
        cls, task: FileTranscriptionTask
    ) -> DetailedTranscriptionResult:
        model = cls._load_openai_whisper_model(task)
        stable_whisper.modify_model(model)
        result: WhisperResult = model.transcribe(
            audio=whisper_audio.load_audio(task.file_path),
            language=task.transcription_options.language,
            task=task.transcription_options.task.value,
            temperature=DEFAULT_WHISPER_TEMPERATURE,
            beam_size=5,
            best_of=5,
            patience=1.0,
            initial_prompt=task.transcription_options.initial_prompt,
            no_speech_threshold=0.4,
            fp16=False,
        )
        segments: list[Segment] = []
        words: list[DetailedTranscriptionWord] = []
        for segment_ordinal, segment in enumerate(result.segments):
            segments.append(
                Segment(
                    start=int(segment.start * 1000),
                    end=int(segment.end * 1000),
                    text=segment.text,
                    translation="",
                )
            )
            for word in segment.words:
                text = word.word.strip()
                if not text:
                    continue
                words.append(
                    DetailedTranscriptionWord(
                        source_segment_ordinal=segment_ordinal,
                        start_ms=int(word.start * 1000),
                        end_ms=int(word.end * 1000),
                        text=text,
                    )
                )
        return DetailedTranscriptionResult(tuple(segments), tuple(words))

    @classmethod
    def _load_openai_whisper_model(cls, task: FileTranscriptionTask):
        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        if force_cpu != "false":
            os.environ["CUDA_VISIBLE_DEVICES"] = ""

        use_cuda = torch.cuda.is_available() and force_cpu == "false"

        device = "cuda" if use_cuda else "cpu"

        # Monkeypatch torch.load to use weights_only=False for PyTorch 2.6+
        # This is required for loading Whisper models with the newer PyTorch versions
        original_torch_load = torch.load

        def patched_torch_load(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return original_torch_load(*args, **kwargs)

        torch.load = patched_torch_load
        try:
            model = whisper.load_model(task.model_path, device=device)
        finally:
            torch.load = original_torch_load
        return model

    @property
    def cleanup_complete(self) -> bool:
        """True only when resources are closed, or cancellation prevented startup."""
        with self._lifecycle_lock:
            return self._cleanup_done.is_set() or (
                self.stopped and not self._transcription_entered
            )

    def request_cancel(self) -> None:
        """Record cancellation without waiting for process/resource cleanup."""
        with self._lifecycle_lock:
            self.stopped = True

    def wait_for_cleanup(self, timeout: float) -> bool:
        """Wait boundedly for startup replay or another cleanup owner."""
        if self.cleanup_complete:
            return True
        self._cleanup_done.wait(max(0, timeout))
        return self.cleanup_complete

    @pyqtSlot()
    def dispose_in_owner_thread(self) -> None:
        """Schedule QObject destruction only while executing on its Qt thread."""
        if QThread.currentThread() is not self.thread():
            raise RuntimeError("Worker disposal must run on its owning Qt thread")
        if self.cleanup_complete:
            self.deleteLater()

    def stop(self):
        with self._lifecycle_lock:
            # This is a durable request, including before process publication.
            self.stopped = True
            if self._cleanup_done.is_set():
                return
            if not self.started_process and self._cleanup_error is None:
                # Startup owns unpublished resources until cancellation replay.
                # A post-reap cleanup error, however, must remain retryable.
                return

        self._cleanup_transcription(cancel=True)

    def read_line(self, pipe: Connection):
        while True:
            try:
                line = pipe.recv().strip()

                # Uncomment to debug
                # print(f"*** DEBUG ***: {line}")

            except (EOFError, BrokenPipeError, ConnectionResetError, OSError):
                # Connection closed, broken, or process crashed (Windows RPC errors raise OSError)
                break
            except Exception as e:
                logging.debug(f"Error reading from pipe: {e}")
                break

            if line == self.READ_LINE_THREAD_STOP_TOKEN:
                return

            if line.startswith("segments = "):
                segments_dict = json.loads(line[11:])
                segments = [
                    Segment(
                        start=segment.get("start"),
                        end=segment.get("end"),
                        text=segment.get("text"),
                        translation="",
                    )
                    for segment in segments_dict
                ]
                self.segments = segments
            elif line.startswith("detailed_result = "):
                payload = json.loads(line[18:])
                self.segments = [
                    Segment(
                        start=segment.get("start"),
                        end=segment.get("end"),
                        text=segment.get("text"),
                        translation="",
                    )
                    for segment in payload.get("segments", [])
                ]
                self.detailed_words = [
                    DetailedTranscriptionWord(
                        source_segment_ordinal=word.get("source_segment_ordinal"),
                        start_ms=word.get("start_ms"),
                        end_ms=word.get("end_ms"),
                        text=word.get("text"),
                    )
                    for word in payload.get("words", [])
                ]
            elif line.startswith("error = "):
                self.error_message = line[8:]
            else:
                try:
                    match = PROGRESS_REGEX.search(line)
                    if match is not None:
                        progress = int(match.group().strip("%"))
                        self.progress.emit((progress, 100))
                except ValueError:
                    logging.debug("whisper (stderr): %s", line)
                    continue


class DetailedWhisperFileTranscriber(WhisperFileTranscriber):
    """Meeting-v2 rich path preserving phrase segments and timed words."""

    @classmethod
    def transcribe_whisper(
        cls, stderr_conn: Connection, task: FileTranscriptionTask
    ) -> None:
        cls._transcribe_whisper_worker(stderr_conn, task, detailed=True)
