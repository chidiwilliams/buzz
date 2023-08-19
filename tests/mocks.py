from buzz.transcriber import (
    FileTranscriptionTask,
    TranscriptionOptions,
    FileTranscriptionOptions,
)


def get_test_asset(filename: str):
    return os.path.join(os.path.dirname(__file__), "../testdata/", filename)


mock_tasks = [
    FileTranscriptionTask(
        file_path="",
        transcription_options=TranscriptionOptions(),
        file_transcription_options=FileTranscriptionOptions(file_paths=[]),
        model_path="",
        status=FileTranscriptionTask.Status.COMPLETED,
    ),
    FileTranscriptionTask(
        file_path="",
        transcription_options=TranscriptionOptions(),
        file_transcription_options=FileTranscriptionOptions(file_paths=[]),
        model_path="",
        status=FileTranscriptionTask.Status.CANCELED,
    ),
    FileTranscriptionTask(
        file_path="",
        transcription_options=TranscriptionOptions(),
        file_transcription_options=FileTranscriptionOptions(file_paths=[]),
        model_path="",
        status=FileTranscriptionTask.Status.FAILED,
        error="Error",
    ),
]
