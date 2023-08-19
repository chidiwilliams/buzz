import pathlib
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QPushButton, QToolBar
from pytestqt.qtbot import QtBot

from buzz.transcriber import (
    FileTranscriptionTask,
    FileTranscriptionOptions,
    TranscriptionOptions,
    Segment,
)
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    TranscriptionSegmentsEditorWidget,
)
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)


class TestTranscriptionViewerWidget:
    @pytest.fixture()
    def task(self) -> FileTranscriptionTask:
        return FileTranscriptionTask(
            id=0,
            file_path="testdata/whisper-french.mp3",
            file_transcription_options=FileTranscriptionOptions(
                file_paths=["testdata/whisper-french.mp3"]
            ),
            transcription_options=TranscriptionOptions(),
            segments=[Segment(40, 299, "Bien"), Segment(299, 329, "venue dans")],
            model_path="",
        )

    def test_should_display_segments(self, qtbot: QtBot, task):
        widget = TranscriptionViewerWidget(
            transcription_task=task, open_transcription_output=False
        )
        qtbot.add_widget(widget)

        assert widget.windowTitle() == "whisper-french.mp3"

        editor = widget.findChild(TranscriptionSegmentsEditorWidget)
        assert isinstance(editor, TranscriptionSegmentsEditorWidget)

        assert editor.item(0, 0).text() == "00:00:00.040"
        assert editor.item(0, 1).text() == "00:00:00.299"
        assert editor.item(0, 2).text() == "Bien"

    def test_should_update_segment_text(self, qtbot, task):
        widget = TranscriptionViewerWidget(
            transcription_task=task, open_transcription_output=False
        )
        qtbot.add_widget(widget)

        editor = widget.findChild(TranscriptionSegmentsEditorWidget)
        assert isinstance(editor, TranscriptionSegmentsEditorWidget)

        # Change text
        editor.item(0, 2).setText("Biens")
        assert task.segments[0].text == "Biens"

        # Undo
        toolbar = widget.findChild(QToolBar)
        undo_action, redo_action = toolbar.actions()

        undo_action.trigger()
        assert task.segments[0].text == "Bien"

        redo_action.trigger()
        assert task.segments[0].text == "Biens"

    def test_should_export_segments(self, tmp_path: pathlib.Path, qtbot: QtBot, task):
        widget = TranscriptionViewerWidget(
            transcription_task=task, open_transcription_output=False
        )
        qtbot.add_widget(widget)

        export_button = widget.findChild(QPushButton)
        assert isinstance(export_button, QPushButton)

        output_file_path = tmp_path / "whisper.txt"
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName"
        ) as save_file_name_mock:
            save_file_name_mock.return_value = (str(output_file_path), "")
            export_button.menu().actions()[0].trigger()

        output_file = open(output_file_path, "r", encoding="utf-8")
        assert "Bien\nvenue dans" in output_file.read()
