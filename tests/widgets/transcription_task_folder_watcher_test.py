import os
import shutil
from tempfile import mkdtemp

from pytestqt.qtbot import QtBot

from buzz.model_loader import TranscriptionModel, ModelType
from buzz.transcriber.transcriber import (
    Task,
    DEFAULT_WHISPER_TEMPERATURE,
    FileTranscriptionTask,
    TranscriptionOptions,
    FileTranscriptionOptions,
)
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)
from buzz.widgets.preferences_dialog.models.folder_watch_preferences import (
    FolderWatchPreferences,
)
from buzz.widgets.transcription_task_folder_watcher import (
    TranscriptionTaskFolderWatcher,
)
from tests.audio import test_audio_path


class TestTranscriptionTaskFolderWatcher:
    def default_model(self):
        model_type = next(
            model_type for model_type in ModelType if model_type.is_available()
        )
        return TranscriptionModel(model_type=model_type)

    def test_should_add_task_not_in_tasks(self, qtbot: QtBot):
        input_directory = mkdtemp()
        output_directory = mkdtemp()
        watcher = TranscriptionTaskFolderWatcher(
            tasks={},
            preferences=FolderWatchPreferences(
                enabled=True,
                input_directory=input_directory,
                output_directory=output_directory,
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=self.default_model(),
                    word_level_timings=False,
                    extract_speech=False,
                    temperature=DEFAULT_WHISPER_TEMPERATURE,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )

        shutil.copy(test_audio_path, input_directory)

        with qtbot.wait_signal(watcher.task_found, timeout=10_000) as blocker:
            pass

        task: FileTranscriptionTask = blocker.args[0]
        assert task.file_path == os.path.join(input_directory, "whisper-french.mp3")
        assert task.source == FileTranscriptionTask.Source.FOLDER_WATCH
        assert task.output_directory == output_directory

    def test_should_not_add_task_in_tasks(self, qtbot):
        input_directory = mkdtemp()
        output_directory = mkdtemp()
        tasks = {
            1: FileTranscriptionTask(
                file_path=os.path.join(input_directory, "whisper-french.mp3"),
                transcription_options=TranscriptionOptions(),
                file_transcription_options=FileTranscriptionOptions(file_paths=[]),
                output_directory=output_directory,
                model_path="",
            ),
        }

        watcher = TranscriptionTaskFolderWatcher(
            tasks=tasks,
            preferences=FolderWatchPreferences(
                enabled=True,
                input_directory=input_directory,
                output_directory=output_directory,
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=self.default_model(),
                    word_level_timings=False,
                    extract_speech=False,
                    temperature=DEFAULT_WHISPER_TEMPERATURE,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )

        # Ignored because already in tasks
        shutil.copy(
            test_audio_path,
            os.path.join(input_directory, "whisper-french.mp3"),
        )
        shutil.copy(
            test_audio_path,
            os.path.join(input_directory, "whisper-french2.mp3"),
        )

        with qtbot.wait_signal(watcher.task_found, timeout=10_000) as blocker:
            pass

        task: FileTranscriptionTask = blocker.args[0]
        assert task.file_path == os.path.join(input_directory, "whisper-french2.mp3")
        assert task.source == FileTranscriptionTask.Source.FOLDER_WATCH
        assert task.output_directory == output_directory

    def test_should_find_tasks_in_subfolders(self, qtbot: QtBot):
        input_directory = mkdtemp()
        output_directory = mkdtemp()
        subfolder = os.path.join(input_directory, "subfolder")
        os.makedirs(subfolder)

        watcher = TranscriptionTaskFolderWatcher(
            tasks={},
            preferences=FolderWatchPreferences(
                enabled=True,
                input_directory=input_directory,
                output_directory=output_directory,
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=self.default_model(),
                    word_level_timings=False,
                    extract_speech=False,
                    temperature=DEFAULT_WHISPER_TEMPERATURE,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )

        shutil.copy(test_audio_path, subfolder)

        with qtbot.wait_signal(watcher.task_found, timeout=10_000) as blocker:
            pass

        task: FileTranscriptionTask = blocker.args[0]
        assert task.file_path == os.path.join(subfolder, "whisper-french.mp3")
        assert task.output_directory == os.path.join(output_directory, "subfolder")
        assert os.path.isdir(task.output_directory)

    def test_should_ignore_hidden_directories(self, qtbot: QtBot):
        input_directory = mkdtemp()
        output_directory = mkdtemp()
        hidden_folder = os.path.join(input_directory, ".hidden")
        os.makedirs(hidden_folder)

        watcher = TranscriptionTaskFolderWatcher(
            tasks={},
            preferences=FolderWatchPreferences(
                enabled=True,
                input_directory=input_directory,
                output_directory=output_directory,
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=self.default_model(),
                    word_level_timings=False,
                    extract_speech=False,
                    temperature=DEFAULT_WHISPER_TEMPERATURE,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )

        # Copy to hidden folder (should be ignored)
        shutil.copy(test_audio_path, hidden_folder)
        # Copy to root folder (should be found)
        shutil.copy(
            test_audio_path,
            os.path.join(input_directory, "visible.mp3"),
        )

        with qtbot.wait_signal(watcher.task_found, timeout=10_000) as blocker:
            pass

        task: FileTranscriptionTask = blocker.args[0]
        assert task.file_path == os.path.join(input_directory, "visible.mp3")

    def test_should_ignore_non_media_files(self, qtbot: QtBot):
        input_directory = mkdtemp()
        output_directory = mkdtemp()

        watcher = TranscriptionTaskFolderWatcher(
            tasks={},
            preferences=FolderWatchPreferences(
                enabled=True,
                input_directory=input_directory,
                output_directory=output_directory,
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=self.default_model(),
                    word_level_timings=False,
                    extract_speech=False,
                    temperature=DEFAULT_WHISPER_TEMPERATURE,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )

        # Create non-media files (should be ignored)
        with open(os.path.join(input_directory, "test.txt"), "w") as f:
            f.write("test")
        with open(os.path.join(input_directory, "test.json"), "w") as f:
            f.write("{}")

        # Copy media file (should be found)
        shutil.copy(test_audio_path, input_directory)

        with qtbot.wait_signal(watcher.task_found, timeout=10_000) as blocker:
            pass

        task: FileTranscriptionTask = blocker.args[0]
        assert task.file_path == os.path.join(input_directory, "whisper-french.mp3")

    def test_should_ignore_temp_conversion_files(self, qtbot: QtBot):
        input_directory = mkdtemp()
        output_directory = mkdtemp()

        watcher = TranscriptionTaskFolderWatcher(
            tasks={},
            preferences=FolderWatchPreferences(
                enabled=True,
                input_directory=input_directory,
                output_directory=output_directory,
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=self.default_model(),
                    word_level_timings=False,
                    extract_speech=False,
                    temperature=DEFAULT_WHISPER_TEMPERATURE,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )

        # Create temp conversion file (should be ignored)
        shutil.copy(
            test_audio_path,
            os.path.join(input_directory, "audio.ogg.wav"),
        )

        # Copy normal media file (should be found)
        shutil.copy(test_audio_path, input_directory)

        with qtbot.wait_signal(watcher.task_found, timeout=10_000) as blocker:
            pass

        task: FileTranscriptionTask = blocker.args[0]
        assert task.file_path == os.path.join(input_directory, "whisper-french.mp3")
