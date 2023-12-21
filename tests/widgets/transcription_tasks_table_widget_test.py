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
        self.assert_row_text(
            widget, 0, "whisper-french.mp3", "Whisper (Tiny)", "Transcribe", "Queued"
        )

        task.status = FileTranscriptionTask.Status.IN_PROGRESS
        task.fraction_completed = 0.3524
        widget.upsert_task(task)

        assert widget.rowCount() == 1
        self.assert_row_text(
            widget,
            0,
            "whisper-french.mp3",
            "Whisper (Tiny)",
            "Transcribe",
            "In Progress (35%)",
        )

        task.status = FileTranscriptionTask.Status.COMPLETED
        task.completed_at = datetime.datetime(2023, 4, 12, 0, 0, 10)
        widget.upsert_task(task)

        assert widget.rowCount() == 1
        self.assert_row_text(
            widget,
            0,
            "whisper-french.mp3",
            "Whisper (Tiny)",
            "Transcribe",
            "Completed (5s)",
        )

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
        self.assert_row_text(
            widget, 0, "whisper-french.mp3", "Whisper (Tiny)", "Transcribe", "Completed"
        )

    def test_toggle_column_visibility(self, qtbot, reset_settings):
        widget = TranscriptionTasksTableWidget()
        qtbot.add_widget(widget)

        assert widget.isColumnHidden(TranscriptionTasksTableWidget.Column.TASK_ID.value)
        assert not widget.isColumnHidden(
            TranscriptionTasksTableWidget.Column.FILE_NAME.value
        )
        assert widget.isColumnHidden(TranscriptionTasksTableWidget.Column.MODEL.value)
        assert widget.isColumnHidden(TranscriptionTasksTableWidget.Column.TASK.value)
        assert not widget.isColumnHidden(
            TranscriptionTasksTableWidget.Column.STATUS.value
        )

        # TODO: open context menu and toggle column visibility

    def assert_row_text(
        self,
        widget: TranscriptionTasksTableWidget,
        row: int,
        filename: str,
        model: str,
        task: str,
        status: str,
    ):
        assert widget.item(row, 1).text() == filename
        assert widget.item(row, 2).text() == model
        assert widget.item(row, 3).text() == task
        assert widget.item(row, 4).text() == status
