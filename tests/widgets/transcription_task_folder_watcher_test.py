import os
import shutil
from tempfile import mkdtemp

import pytest
from pytestqt.qtbot import QtBot

from buzz.model_loader import TranscriptionModel, ModelType
from buzz.transcriber.transcriber import (
    Task,
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


@pytest.fixture(autouse=True)
def short_settle_time(monkeypatch):
    monkeypatch.setattr(TranscriptionTaskFolderWatcher, "settle_seconds", 0.3)
    monkeypatch.setattr(
        TranscriptionTaskFolderWatcher, "settle_poll_interval_ms", 50
    )


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

    def test_should_ignore_extracted_speech_files(self, qtbot: QtBot):
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
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )

        # Create extracted speech file (should be ignored)
        shutil.copy(
            test_audio_path,
            os.path.join(input_directory, "video_speech.mp3"),
        )

        # Copy normal media file (should be found)
        shutil.copy(test_audio_path, input_directory)

        with qtbot.wait_signal(watcher.task_found, timeout=10_000) as blocker:
            pass

        task: FileTranscriptionTask = blocker.args[0]
        assert task.file_path == os.path.join(input_directory, "whisper-french.mp3")

    def test_should_set_delete_source_file_when_preference_enabled(self, qtbot: QtBot):
        input_directory = mkdtemp()
        output_directory = mkdtemp()

        watcher = TranscriptionTaskFolderWatcher(
            tasks={},
            preferences=FolderWatchPreferences(
                enabled=True,
                input_directory=input_directory,
                output_directory=output_directory,
                delete_processed_files=True,
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=self.default_model(),
                    word_level_timings=False,
                    extract_speech=False,
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
        assert task.delete_source_file is True

    def test_should_not_set_delete_source_file_when_preference_disabled(self, qtbot: QtBot):
        input_directory = mkdtemp()
        output_directory = mkdtemp()

        watcher = TranscriptionTaskFolderWatcher(
            tasks={},
            preferences=FolderWatchPreferences(
                enabled=True,
                input_directory=input_directory,
                output_directory=output_directory,
                delete_processed_files=False,
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=self.default_model(),
                    word_level_timings=False,
                    extract_speech=False,
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
        assert task.delete_source_file is False

    def test_should_set_original_file_path(self, qtbot: QtBot):
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
        expected_path = os.path.join(input_directory, "whisper-french.mp3")
        assert task.file_path == expected_path
        assert task.original_file_path == expected_path

    def test_should_set_speaker_identification_options(self, qtbot: QtBot):
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
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
                identify_speakers=True,
                speaker_diarizer="sortformer",
                speaker_count=3,
                merge_speaker_sentences=False,
            ),
        )

        shutil.copy(test_audio_path, input_directory)

        with qtbot.wait_signal(watcher.task_found, timeout=10_000) as blocker:
            pass

        task: FileTranscriptionTask = blocker.args[0]
        assert task.identify_speakers is True
        assert task.speaker_diarizer == "sortformer"
        assert task.speaker_count == 3
        assert task.merge_speaker_sentences is False

    def test_should_ignore_media_path_that_cannot_be_read(self, qtbot: QtBot):
        input_directory = mkdtemp()
        output_directory = mkdtemp()
        try:
            os.symlink(
                os.path.join(input_directory, "gone.mp3"),
                os.path.join(input_directory, "dangling.mp3"),
            )
        except (OSError, NotImplementedError):
            pytest.skip("this platform cannot create symlinks")

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
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )

        with qtbot.assert_not_emitted(watcher.task_found):
            watcher.find_tasks()

    def watcher_for(self, input_directory, output_directory):
        return TranscriptionTaskFolderWatcher(
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
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )

    def test_should_settle_copied_file_once_when_copy_sets_mtime_on_close(
        self, qtbot: QtBot
    ):
        # Windows copies (Explorer, SMB) write the data first and set the
        # source's modification time when closing the file, so one copy is
        # seen with two different stamps.
        input_directory = mkdtemp()
        output_directory = mkdtemp()
        watcher = self.watcher_for(input_directory, output_directory)
        found = []
        settled = []
        watcher.task_found.connect(found.append)
        watcher.task_settled.connect(settled.append)

        file_path = os.path.join(input_directory, "copied.mp3")
        shutil.copyfile(test_audio_path, file_path)
        watcher.find_tasks()
        qtbot.wait(100)

        os.utime(file_path, (1_600_000_000, 1_600_000_000))
        watcher.find_tasks()

        qtbot.wait_until(lambda: len(settled) > 0, timeout=5_000)
        qtbot.wait(500)
        watcher.find_tasks()
        qtbot.wait(500)

        assert [task.file_path for task in found] == [file_path]
        assert settled == found

    def test_should_find_file_at_once_but_settle_after_it_stops_growing(
        self, qtbot: QtBot
    ):
        input_directory = mkdtemp()
        output_directory = mkdtemp()
        watcher = self.watcher_for(input_directory, output_directory)
        found = []
        settled = []
        watcher.task_found.connect(found.append)
        watcher.task_settled.connect(settled.append)

        file_path = os.path.join(input_directory, "growing.mp3")
        with open(test_audio_path, "rb") as source:
            data = source.read()

        chunk_size = len(data) // 10 + 1
        with open(file_path, "wb") as target:
            for start in range(0, len(data), chunk_size):
                target.write(data[start : start + chunk_size])
                target.flush()
                watcher.find_tasks()
                qtbot.wait(100)
                assert len(found) == 1
                assert settled == []

        qtbot.wait_until(lambda: len(settled) > 0, timeout=5_000)
        qtbot.wait(500)

        assert settled == found
        assert os.path.getsize(settled[0].file_path) == len(data)

    def test_should_discard_file_removed_before_it_settles(self, qtbot: QtBot):
        input_directory = mkdtemp()
        output_directory = mkdtemp()
        watcher = self.watcher_for(input_directory, output_directory)
        found = []
        discarded = []
        watcher.task_found.connect(found.append)
        watcher.task_discarded.connect(discarded.append)

        file_path = os.path.join(input_directory, "removed.mp3")
        shutil.copyfile(test_audio_path, file_path)
        watcher.find_tasks()
        os.remove(file_path)

        with qtbot.assert_not_emitted(watcher.task_settled, wait=1_000):
            pass

        assert len(found) == 1
        assert discarded == found
        assert watcher.pending_files == {}
        assert not watcher.settle_timer.isActive()

    def test_should_keep_pending_files_when_preferences_are_unchanged(
        self, qtbot: QtBot
    ):
        input_directory = mkdtemp()
        output_directory = mkdtemp()
        watcher = self.watcher_for(input_directory, output_directory)
        found = []
        settled = []
        watcher.task_found.connect(found.append)
        watcher.task_settled.connect(settled.append)

        shutil.copy(test_audio_path, input_directory)
        watcher.find_tasks()

        with qtbot.assert_not_emitted(watcher.task_discarded):
            watcher.set_preferences(
                self.watcher_for(input_directory, output_directory).preferences
            )
            watcher.find_tasks()

        qtbot.wait_until(lambda: len(settled) > 0, timeout=5_000)
        assert settled == found
