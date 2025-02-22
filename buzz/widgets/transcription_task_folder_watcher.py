import logging
import os
from typing import Dict

from PyQt6.QtCore import QFileSystemWatcher, pyqtSignal, QObject

from buzz.store.keyring_store import Key, get_password
from buzz.transcriber.transcriber import FileTranscriptionTask
from buzz.model_loader import ModelDownloader
from buzz.widgets.preferences_dialog.models.folder_watch_preferences import (
    FolderWatchPreferences,
)


class TranscriptionTaskFolderWatcher(QFileSystemWatcher):
    preferences: FolderWatchPreferences
    task_found = pyqtSignal(FileTranscriptionTask)

    # TODO: query db instead of passing tasks
    def __init__(
        self,
        tasks: Dict[int, FileTranscriptionTask],
        preferences: FolderWatchPreferences,
        parent: QObject = None,
    ):
        super().__init__(parent)
        self.tasks = tasks
        self.paths_emitted = set()
        self.set_preferences(preferences)
        self.directoryChanged.connect(self.find_tasks)

    def set_preferences(self, preferences: FolderWatchPreferences):
        self.preferences = preferences
        if len(self.directories()) > 0:
            self.removePaths(self.directories())
        if preferences.enabled:
            self.addPath(preferences.input_directory)
            logging.debug(
                'Watching for media files in "%s"', preferences.input_directory
            )

    def find_tasks(self):
        input_directory = self.preferences.input_directory
        tasks = {task.file_path: task for task in self.tasks.values()}

        if not self.preferences.enabled:
            return

        for dirpath, dirnames, filenames in os.walk(input_directory):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                if (
                    filename.startswith(".")  # hidden files
                    or file_path in tasks  # file already in tasks
                    or file_path in self.paths_emitted  # file already emitted
                ):
                    continue

                openai_access_token = get_password(Key.OPENAI_API_KEY)
                (
                    transcription_options,
                    file_transcription_options,
                ) = self.preferences.file_transcription_options.to_transcription_options(
                    openai_access_token=openai_access_token,
                    file_paths=[file_path],
                )
                model_path = transcription_options.model.get_local_model_path()

                if model_path is None:
                    ModelDownloader(model=transcription_options.model).run()
                    model_path = transcription_options.model.get_local_model_path()

                task = FileTranscriptionTask(
                    file_path=file_path,
                    transcription_options=transcription_options,
                    file_transcription_options=file_transcription_options,
                    model_path=model_path,
                    output_directory=self.preferences.output_directory,
                    source=FileTranscriptionTask.Source.FOLDER_WATCH,
                )
                self.task_found.emit(task)
                self.paths_emitted.add(file_path)

            # Don't traverse into subdirectories
            break
