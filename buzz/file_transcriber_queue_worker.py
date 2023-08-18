import datetime
import logging
import multiprocessing
import queue
from typing import Optional, Tuple, List

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from buzz.model_loader import ModelType
from buzz.transcriber import (
    FileTranscriptionTask,
    FileTranscriber,
    WhisperCppFileTranscriber,
    OpenAIWhisperAPIFileTranscriber,
    WhisperFileTranscriber,
    Segment,
)


class FileTranscriberQueueWorker(QObject):
    tasks_queue: multiprocessing.Queue
    current_task: Optional[FileTranscriptionTask] = None
    current_transcriber: Optional[FileTranscriber] = None
    current_transcriber_thread: Optional[QThread] = None
    task_updated = pyqtSignal(FileTranscriptionTask)
    completed = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.tasks_queue = queue.Queue()
        self.canceled_tasks = set()

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

            if self.current_task.id in self.canceled_tasks:
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
        self.current_transcriber.error.connect(self.on_task_error)

        self.current_transcriber.completed.connect(self.on_task_completed)

        # Wait for next item on the queue
        self.current_transcriber.error.connect(self.run)
        self.current_transcriber.completed.connect(self.run)

        self.current_task.started_at = datetime.datetime.now()
        self.current_transcriber_thread.start()

    def add_task(self, task: FileTranscriptionTask):
        if task.queued_at is None:
            task.queued_at = datetime.datetime.now()

        self.tasks_queue.put(task)
        task.status = FileTranscriptionTask.Status.QUEUED
        self.task_updated.emit(task)

    def cancel_task(self, task_id: int):
        self.canceled_tasks.add(task_id)

        if self.current_task.id == task_id:
            if self.current_transcriber is not None:
                self.current_transcriber.stop()

    @pyqtSlot(Exception)
    def on_task_error(self, error: Exception):
        if (
            self.current_task is not None
            and self.current_task.id not in self.canceled_tasks
        ):
            self.current_task.status = FileTranscriptionTask.Status.FAILED
            self.current_task.error = str(error)
            self.task_updated.emit(self.current_task)

    @pyqtSlot(tuple)
    def on_task_progress(self, progress: Tuple[int, int]):
        if self.current_task is not None:
            self.current_task.status = FileTranscriptionTask.Status.IN_PROGRESS
            self.current_task.fraction_completed = progress[0] / progress[1]
            self.task_updated.emit(self.current_task)

    @pyqtSlot(list)
    def on_task_completed(self, segments: List[Segment]):
        if self.current_task is not None:
            self.current_task.status = FileTranscriptionTask.Status.COMPLETED
            self.current_task.segments = segments
            self.current_task.completed_at = datetime.datetime.now()
            self.task_updated.emit(self.current_task)

    def stop(self):
        self.tasks_queue.put(None)
        if self.current_transcriber is not None:
            self.current_transcriber.stop()
