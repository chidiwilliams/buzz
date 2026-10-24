import logging
import os
import time
from typing import Dict, Tuple

from PyQt6.QtCore import QFileSystemWatcher, QTimer, pyqtSignal, QObject

from buzz.store.keyring_store import Key, get_password
from buzz.transcriber.transcriber import (
    FileTranscriptionTask,
    SUPPORTED_EXTENSIONS,
)
from buzz.model_loader import ModelDownloader
from buzz.widgets.preferences_dialog.models.folder_watch_preferences import (
    FolderWatchPreferences,
)


class TranscriptionTaskFolderWatcher(QFileSystemWatcher):
    preferences: FolderWatchPreferences
    # A new media file was found and its task can be listed as queued
    task_found = pyqtSignal(FileTranscriptionTask)
    # The file of a found task has settled and can be transcribed
    task_settled = pyqtSignal(FileTranscriptionTask)
    # The file of a found task went away before it settled
    task_discarded = pyqtSignal(FileTranscriptionTask)

    # A found file is transcribed only once its size and modification time
    # have not changed for this long. A copy, especially over a network share,
    # changes them several times before it is done; Windows sets the final
    # modification time only when the copy closes the file.
    settle_seconds = 30.0
    settle_poll_interval_ms = 5000

    # TODO: query db instead of passing tasks
    def __init__(
        self,
        tasks: Dict[int, FileTranscriptionTask],
        preferences: FolderWatchPreferences,
        parent: QObject = None,
    ):
        super().__init__(parent)
        self.tasks = tasks
        self.paths_emitted = {}
        # file path -> (task, file stamp, monotonic time the stamp was first seen)
        self.pending_files: Dict[
            str, Tuple[FileTranscriptionTask, Tuple[int, float], float]
        ] = {}
        self.settle_timer = QTimer(self)
        self.settle_timer.setInterval(self.settle_poll_interval_ms)
        self.settle_timer.timeout.connect(self.check_pending_files)
        self.set_preferences(preferences)
        self.directoryChanged.connect(self.find_tasks)

    def set_preferences(self, preferences: FolderWatchPreferences):
        # Pending tasks were built from the old preferences. Saving unrelated
        # preferences must not cancel and re-add files that are still copying.
        if preferences != getattr(self, "preferences", None):
            self.discard_pending_files()
        self.preferences = preferences
        if len(self.directories()) > 0:
            self.removePaths(self.directories())
        if preferences.enabled and preferences.input_directory:
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

        if not self.preferences.enabled or not self.preferences.input_directory:
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
                ):
                    continue

                try:
                    file_stamp = (
                        os.path.getsize(file_path),
                        os.path.getmtime(file_path),
                    )
                except OSError:
                    # A dangling symlink, or a file removed since os.walk listed
                    # it. There is nothing to transcribe and nothing to stamp.
                    continue

                if self.paths_emitted.get(file_path) == file_stamp:
                    continue

                pending = self.pending_files.get(file_path)
                if pending is None:
                    task = self.create_task(file_path)
                    self.pending_files[file_path] = (
                        task,
                        file_stamp,
                        time.monotonic(),
                    )
                    self.task_found.emit(task)
                elif pending[1] != file_stamp:
                    self.pending_files[file_path] = (
                        pending[0],
                        file_stamp,
                        time.monotonic(),
                    )

            # Filter out hidden directories and add new subdirectories to the watcher
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for dirname in dirnames:
                subdir_path = os.path.join(dirpath, dirname)
                if subdir_path not in self.directories():
                    self.addPath(subdir_path)

        if self.pending_files and not self.settle_timer.isActive():
            self.settle_timer.start()

    def check_pending_files(self):
        if not self.preferences.enabled or not self.preferences.input_directory:
            self.discard_pending_files()
            return

        now = time.monotonic()
        for file_path, (task, file_stamp, stamp_since) in list(
            self.pending_files.items()
        ):
            try:
                current_stamp = (
                    os.path.getsize(file_path),
                    os.path.getmtime(file_path),
                )
            except OSError:
                # Removed or renamed before it settled
                del self.pending_files[file_path]
                self.task_discarded.emit(task)
                continue

            if current_stamp != file_stamp:
                self.pending_files[file_path] = (task, current_stamp, now)
                continue

            if now - stamp_since < self.settle_seconds:
                continue

            del self.pending_files[file_path]
            self.paths_emitted[file_path] = current_stamp
            self.task_settled.emit(task)

        if not self.pending_files:
            self.settle_timer.stop()

    def discard_pending_files(self):
        self.settle_timer.stop()
        pending_tasks = [task for task, _, _ in self.pending_files.values()]
        self.pending_files.clear()
        for task in pending_tasks:
            self.task_discarded.emit(task)

    def create_task(self, file_path: str) -> FileTranscriptionTask:
        input_directory = self.preferences.input_directory
        dirpath = os.path.dirname(file_path)

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

        return FileTranscriptionTask(
            file_path=file_path,
            original_file_path=file_path,
            transcription_options=transcription_options,
            file_transcription_options=file_transcription_options,
            model_path=model_path,
            output_directory=output_directory,
            source=FileTranscriptionTask.Source.FOLDER_WATCH,
            delete_source_file=self.preferences.delete_processed_files,
            identify_speakers=self.preferences.identify_speakers,
            speaker_diarizer=self.preferences.speaker_diarizer,
            speaker_count=self.preferences.speaker_count,
            merge_speaker_sentences=self.preferences.merge_speaker_sentences,
        )
