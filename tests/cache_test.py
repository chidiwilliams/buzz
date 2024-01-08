from buzz.cache import TasksCache
from buzz.transcriber.transcriber import (
    FileTranscriptionOptions,
    FileTranscriptionTask,
    TranscriptionOptions,
)


class TestTasksCache:
    def test_should_save_and_load(self, tmp_path):
        cache = TasksCache(cache_dir=str(tmp_path))
        tasks = [
            FileTranscriptionTask(
                file_path="1.mp3",
                transcription_options=TranscriptionOptions(),
                file_transcription_options=FileTranscriptionOptions(
                    file_paths=["1.mp3"]
                ),
                model_path="",
            ),
            FileTranscriptionTask(
                file_path="2.mp3",
                transcription_options=TranscriptionOptions(),
                file_transcription_options=FileTranscriptionOptions(
                    file_paths=["2.mp3"]
                ),
                model_path="",
            ),
        ]
        cache.save(tasks)
        assert cache.load() == tasks
