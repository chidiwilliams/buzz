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

# Supported media file extensions (audio and video)
SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac",  # audio
    ".mp4", ".webm", ".ogm", ".mov", ".mkv", ".avi", ".wmv",  # video
}


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
            # Add the input directory and all subdirectories to the watcher
            for dirpath, dirnames, _ in os.walk(preferences.input_directory):
                # Skip hidden directories
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                self.addPath(dirpath)
            logging.debug(
                'Watching for media files in "%s" and subdirectories',
                preferences.input_directory,
            )

    def find_tasks(self):
        input_directory = self.preferences.input_directory
        tasks = {task.file_path: task for task in self.tasks.values()}

        if not self.preferences.enabled:
            return

        for dirpath, dirnames, filenames in os.walk(input_directory):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                file_ext = os.path.splitext(filename)[1].lower()

                # Check for temp conversion files (e.g., .ogg.wav)
                name_without_ext = os.path.splitext(filename)[0]
                secondary_ext = os.path.splitext(name_without_ext)[1].lower()
                is_temp_conversion_file = secondary_ext in SUPPORTED_EXTENSIONS

                if (
                    filename.startswith(".")  # hidden files
                    or file_ext not in SUPPORTED_EXTENSIONS  # non-media files
                    or is_temp_conversion_file  # temp conversion files like .ogg.wav
                    or "_speech.mp3" in filename  # extracted speech output files
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

                # Preserve subdirectory structure in output directory
                relative_path = os.path.relpath(dirpath, input_directory)
                if relative_path == ".":
                    output_directory = self.preferences.output_directory
                else:
                    output_directory = os.path.join(
                        self.preferences.output_directory, relative_path
                    )

                # Create output directory if it doesn't exist
                os.makedirs(output_directory, exist_ok=True)

                task = FileTranscriptionTask(
                    file_path=file_path,
                    original_file_path=file_path,
                    transcription_options=transcription_options,
                    file_transcription_options=file_transcription_options,
                    model_path=model_path,
                    output_directory=output_directory,
                    source=FileTranscriptionTask.Source.FOLDER_WATCH,
                )
                self.task_found.emit(task)
                self.paths_emitted.add(file_path)

            # Filter out hidden directories and add new subdirectories to the watcher
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for dirname in dirnames:
                subdir_path = os.path.join(dirpath, dirname)
                if subdir_path not in self.directories():
                    self.addPath(subdir_path)
