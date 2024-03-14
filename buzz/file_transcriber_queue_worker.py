import logging
import multiprocessing
import queue
from typing import Optional, Tuple, List, Set
from uuid import UUID

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from buzz.model_loader import ModelType
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.openai_whisper_api_file_transcriber import (
    OpenAIWhisperAPIFileTranscriber,
)
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment
from buzz.transcriber.whisper_cpp_file_transcriber import WhisperCppFileTranscriber
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

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.tasks_queue = queue.Queue()
        self.canceled_tasks: Set[UUID] = set()

    @pyqtSlot()
    def run(self):
        logging.debug("Waiting for next transcription task")

        # Get next non-canceled task from queue
        while True:
            self.current_task: Optional[FileTranscriptionTask] = self.tasks_queue.get()

            # Stop listening when a "None" task is received
            if self.current_task is None:
                self.completed.emit()
                return

            if self.current_task.uid in self.canceled_tasks:
                continue

            break

        logging.debug("Starting next transcription task")

        model_type = self.current_task.transcription_options.model.model_type
        if model_type == ModelType.WHISPER_CPP:
            self.current_transcriber = WhisperCppFileTranscriber(task=self.current_task)
        elif model_type == ModelType.OPEN_AI_WHISPER_API:
            self.current_transcriber = OpenAIWhisperAPIFileTranscriber(
                task=self.current_task
            )
        elif (
            model_type == ModelType.HUGGING_FACE
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
        self.current_transcriber.error.connect(self.run)
        self.current_transcriber.completed.connect(self.run)

        self.task_started.emit(self.current_task)
        self.current_transcriber_thread.start()

    def add_task(self, task: FileTranscriptionTask):
        self.tasks_queue.put(task)

    def cancel_task(self, task_id: UUID):
        self.canceled_tasks.add(task_id)

        if self.current_task.uid == task_id:
            if self.current_transcriber is not None:
                self.current_transcriber.stop()

    def on_task_error(self, error: str):
        if (
            self.current_task is not None
            and self.current_task.uid not in self.canceled_tasks
        ):
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

    def stop(self):
        self.tasks_queue.put(None)
        if self.current_transcriber is not None:
            self.current_transcriber.stop()
