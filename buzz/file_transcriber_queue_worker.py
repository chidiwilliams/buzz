import logging
import multiprocessing
import os
import queue
import ssl
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Set
from uuid import UUID

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
    import subprocess
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


def _speech_extraction_worker(conn, file_path: str, speech_path: str, device: str) -> None:
    """Extract speech with demucs in a dedicated process.
    """
    try:
        def callback(progress):
            try:
                conn.send(
                    ("progress", progress["segment_offset"], progress["audio_length"])
                )
            except Exception:
                pass

        separator = demucsApi.Separator(
            device=device,
            progress=True,
            callback=callback,
        )
        _origin, separated = separator.separate_audio_file(Path(file_path))
        demucsApi.save_audio(separated["vocals"], speech_path, separator.samplerate)
        conn.send(("done", None))
    except IndexError as e:
        # File has no audio stream (e.g. a silent video). Signal the parent to
        # skip speech extraction and transcribe the original file as-is.
        conn.send(("no_audio", str(e)))
    except Exception as e:
        logging.error(f"Error during speech extraction: {e}", exc_info=True)
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


class FileTranscriberQueueWorker(QObject):
    tasks_queue: multiprocessing.Queue
    current_task: Optional[FileTranscriptionTask] = None
    current_transcriber: Optional[FileTranscriber] = None
    current_transcriber_thread: Optional[QThread] = None

    task_started = pyqtSignal(FileTranscriptionTask)
    task_progress = pyqtSignal(FileTranscriptionTask, float)
    task_download_progress = pyqtSignal(FileTranscriptionTask, float)
    task_completed = pyqtSignal(FileTranscriptionTask, list)
    task_error = pyqtSignal(FileTranscriptionTask, str)

    completed = pyqtSignal()
    trigger_run = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.tasks_queue = queue.Queue()
        self.canceled_tasks: Set[UUID] = set()
        self.current_transcriber = None
        self.speech_path = None
        self.speech_extractor_process = None
        self.is_running = False
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

        # Clean up of previous run.
        if self.current_transcriber is not None:
            self.current_transcriber.stop()
            self.current_transcriber = None

        # Get next non-canceled task from queue
        while True:
            self.current_task: Optional[FileTranscriptionTask] = self.tasks_queue.get()

            # Stop listening when a "None" task is received
            if self.current_task is None:
                self.is_running = False
                self.completed.emit()
                return

            if self.current_task.uid in self.canceled_tasks:
                continue

            break

        # Set is_running AFTER we have a valid task to process
        self.is_running = True

        if self.current_task.transcription_options.extract_speech:
            logging.debug("Will extract speech")

            # Force CPU if specified, otherwise use CUDA if available
            force_cpu = os.getenv("BUZZ_FORCE_CPU", "false").lower() == "true"
            if force_cpu:
                device = "cpu"
            else:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"

            task_file_path = Path(self.current_task.file_path)
            speech_path = task_file_path.with_name(f"{task_file_path.stem}_speech.mp3")

            status = self._extract_speech(str(task_file_path), str(speech_path), device)

            if status == "error":
                self.task_error.emit(
                    self.current_task,
                    _("Speech extraction failed! Check your internet connection — a model may need to be downloaded."),
                )
                self.is_running = False
                return

            if status == "ok":
                self.speech_path = speech_path
                # Remember the original audio path: file_path is about to point
                # at the temporary "_speech.mp3", which is deleted once the
                # transcription completes. Plugins (e.g. the transcript resizer)
                # need the original file in their post-completion hooks.
                if not self.current_task.original_file_path:
                    self.current_task.original_file_path = str(task_file_path)
                self.current_task.file_path = str(speech_path)
            # status == "no_audio": transcribe the original file as-is.

        # Let plugins process / replace the source audio before transcription.
        # Runs on this worker thread; plugins may overwrite current_task.file_path.
        if self.plugin_manager is not None:
            try:
                self.plugin_manager.run_before_transcription(self.current_task)
            except Exception as e:
                logging.error(f"Plugin before_transcription failed: {e}", exc_info=True)

        logging.debug("Starting next transcription task")
        self.task_progress.emit(self.current_task, 0)

        model_type = self.current_task.transcription_options.model.model_type
        if model_type == ModelType.OPEN_AI_WHISPER_API:
            self.current_transcriber = OpenAIWhisperAPIFileTranscriber(
                task=self.current_task
            )
        elif (
            model_type == ModelType.WHISPER_CPP
            or model_type == ModelType.HUGGING_FACE
            or model_type == ModelType.WHISPER
            or model_type == ModelType.FASTER_WHISPER
        ):
            self.current_transcriber = WhisperFileTranscriber(task=self.current_task)
        else:
            raise Exception(f"Unknown model type: {model_type}")

        self.current_transcriber_thread = QThread(self)

        self.current_transcriber.moveToThread(self.current_transcriber_thread)

        self.current_transcriber_thread.started.connect(self.current_transcriber.run)
        self.current_transcriber.completed.connect(self.current_transcriber_thread.quit)
        self.current_transcriber.error.connect(self.current_transcriber_thread.quit)

        self.current_transcriber.completed.connect(self.current_transcriber.deleteLater)
        self.current_transcriber.error.connect(self.current_transcriber.deleteLater)
        self.current_transcriber_thread.finished.connect(
            self.current_transcriber_thread.deleteLater
        )

        self.current_transcriber.progress.connect(self.on_task_progress)
        self.current_transcriber.download_progress.connect(
            self.on_task_download_progress
        )
        self.current_transcriber.error.connect(self.on_task_error)

        self.current_transcriber.completed.connect(self.on_task_completed)

        # Wait for next item on the queue
        self.current_transcriber.error.connect(lambda: self._on_task_finished())
        self.current_transcriber.completed.connect(lambda: self._on_task_finished())

        self.task_started.emit(self.current_task)
        self.current_transcriber_thread.start()

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
                            self.current_task,
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

    def _on_task_finished(self):
        """Called when a task completes or errors, resets state and triggers next run"""
        self.is_running = False
        # Use signal to avoid blocking in signal handler context
        self.trigger_run.emit()

    def add_task(self, task: FileTranscriptionTask):
        # Remove from canceled tasks if it was previously canceled (for restart functionality)
        if task.uid in self.canceled_tasks:
            self.canceled_tasks.remove(task.uid)

        self.tasks_queue.put(task)
        # If the worker is not currently running, trigger it to start processing
        # Use signal to avoid blocking the main thread
        if not self.is_running:
            self.trigger_run.emit()

    def cancel_task(self, task_id: UUID):
        self.canceled_tasks.add(task_id)

        if self.current_task is not None and self.current_task.uid == task_id:
            self._terminate_speech_extractor_process()

            if self.current_transcriber is not None:
                self.current_transcriber.stop()

            if self.current_transcriber_thread is not None:
                if not self.current_transcriber_thread.wait(5000):
                    logging.warning("Transcriber thread did not terminate gracefully")
                    self.current_transcriber_thread.terminate()

    def on_task_error(self, error: str):
        if (
            self.current_task is not None
            and self.current_task.uid not in self.canceled_tasks
        ):
            # Check if the error indicates cancellation
            if "canceled" in error.lower() or "cancelled" in error.lower():
                self.current_task.status = FileTranscriptionTask.Status.CANCELED
                self.current_task.error = error
            else:
                self.current_task.status = FileTranscriptionTask.Status.FAILED
                self.current_task.error = error
            self.task_error.emit(self.current_task, error)

    @pyqtSlot(tuple)
    def on_task_progress(self, progress: Tuple[int, int]):
        if self.current_task is not None:
            self.task_progress.emit(self.current_task, progress[0] / progress[1])

    def on_task_download_progress(self, fraction_downloaded: float):
        if self.current_task is not None:
            self.task_download_progress.emit(self.current_task, fraction_downloaded)

    @pyqtSlot(list)
    def on_task_completed(self, segments: List[Segment]):
        if self.current_task is not None:
            self.task_completed.emit(self.current_task, segments)

        if self.speech_path is not None:
            try:
                Path(self.speech_path).unlink()
            except Exception:
                pass
            self.speech_path = None

    def stop(self):
        self.tasks_queue.put(None)
        if self.current_transcriber is not None:
            self.current_transcriber.stop()

        # Terminate the speech extraction process if one is still running.
        self._terminate_speech_extractor_process()
