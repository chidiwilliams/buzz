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
        self.is_running = False
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

            def separator_progress_callback(progress):
                self.task_progress.emit(self.current_task, int(progress["segment_offset"] * 100) / int(progress["audio_length"] * 100))

            try:
                separator = demucsApi.Separator(
                    progress=True,
                    callback=separator_progress_callback,
                )
                _, separated = separator.separate_audio_file(Path(self.current_task.file_path))

                task_file_path = Path(self.current_task.file_path)
                self.speech_path = task_file_path.with_name(f"{task_file_path.stem}_speech.mp3")
                demucsApi.save_audio(separated["vocals"], self.speech_path, separator.samplerate)

                self.current_task.file_path = str(self.speech_path)
            except Exception as e:
                logging.error(f"Error during speech extraction: {e}", exc_info=True)

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
