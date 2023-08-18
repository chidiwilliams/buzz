import datetime

from pytestqt.qtbot import QtBot

from buzz.transcriber import (
    FileTranscriptionTask,
    TranscriptionOptions,
    FileTranscriptionOptions,
)
from buzz.widgets.transcription_tasks_table_widget import TranscriptionTasksTableWidget


class TestTranscriptionTasksTableWidget:
    def test_upsert_task(self, qtbot: QtBot):
        widget = TranscriptionTasksTableWidget()
        qtbot.add_widget(widget)

        task = FileTranscriptionTask(
            id=0,
            file_path="testdata/whisper-french.mp3",
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(
                file_paths=["testdata/whisper-french.mp3"]
            ),
            model_path="",
            status=FileTranscriptionTask.Status.QUEUED,
        )
        task.queued_at = datetime.datetime(2023, 4, 12, 0, 0, 0)
        task.started_at = datetime.datetime(2023, 4, 12, 0, 0, 5)

        widget.upsert_task(task)

        assert widget.rowCount() == 1
        assert widget.item(0, 1).text() == "whisper-french.mp3"
        assert widget.item(0, 2).text() == "Queued"

        task.status = FileTranscriptionTask.Status.IN_PROGRESS
        task.fraction_completed = 0.3524
        widget.upsert_task(task)

        assert widget.rowCount() == 1
        assert widget.item(0, 1).text() == "whisper-french.mp3"
        assert widget.item(0, 2).text() == "In Progress (35%)"

        task.status = FileTranscriptionTask.Status.COMPLETED
        task.completed_at = datetime.datetime(2023, 4, 12, 0, 0, 10)
        widget.upsert_task(task)

        assert widget.rowCount() == 1
        assert widget.item(0, 1).text() == "whisper-french.mp3"
        assert widget.item(0, 2).text() == "Completed (5s)"

    def test_upsert_task_no_timings(self, qtbot: QtBot):
        widget = TranscriptionTasksTableWidget()
        qtbot.add_widget(widget)

        task = FileTranscriptionTask(
            id=0,
            file_path="testdata/whisper-french.mp3",
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(
                file_paths=["testdata/whisper-french.mp3"]
            ),
            model_path="",
            status=FileTranscriptionTask.Status.COMPLETED,
        )
        widget.upsert_task(task)

        assert widget.rowCount() == 1
        assert widget.item(0, 1).text() == "whisper-french.mp3"
        assert widget.item(0, 2).text() == "Completed"
