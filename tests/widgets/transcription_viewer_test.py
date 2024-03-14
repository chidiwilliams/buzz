import pathlib
import uuid
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QPushButton
from pytestqt.qtbot import QtBot

from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    TranscriptionSegmentsEditorWidget,
)
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)


class TestTranscriptionViewerWidget:
    @pytest.fixture()
    def transcription(
        self, transcription_dao, transcription_segment_dao
    ) -> Transcription:
        id = uuid.uuid4()
        transcription_dao.insert(
            Transcription(
                id=str(id),
                status="completed",
                file="testdata/whisper-french.mp3",
                task=Task.TRANSCRIBE.value,
                model_type=ModelType.WHISPER.value,
                whisper_model_size=WhisperModelSize.SMALL.value,
            )
        )
        transcription_segment_dao.insert(TranscriptionSegment(40, 299, "Bien", str(id)))
        transcription_segment_dao.insert(
            TranscriptionSegment(299, 329, "venue dans", str(id))
        )

        return transcription_dao.find_by_id(str(id))

    def test_should_display_segments(self, qtbot: QtBot, transcription):
        widget = TranscriptionViewerWidget(transcription)
        qtbot.add_widget(widget)

        assert widget.windowTitle() == "whisper-french.mp3"

        editor = widget.findChild(TranscriptionSegmentsEditorWidget)
        assert isinstance(editor, TranscriptionSegmentsEditorWidget)

        assert editor.model().index(0, 1).data() == 299
        assert editor.model().index(0, 2).data() == 40
        assert editor.model().index(0, 3).data() == "Bien"

    def test_should_update_segment_text(self, qtbot, transcription):
        widget = TranscriptionViewerWidget(transcription)
        qtbot.add_widget(widget)

        editor = widget.findChild(TranscriptionSegmentsEditorWidget)
        assert isinstance(editor, TranscriptionSegmentsEditorWidget)

        editor.model().setData(editor.model().index(0, 3), "Biens")

    def test_should_export_segments(
        self, tmp_path: pathlib.Path, qtbot: QtBot, transcription
    ):
        widget = TranscriptionViewerWidget(transcription)
        qtbot.add_widget(widget)

        export_button = widget.findChild(QPushButton)
        assert isinstance(export_button, QPushButton)

        output_file_path = tmp_path / "whisper.txt"
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName"
        ) as save_file_name_mock:
            save_file_name_mock.return_value = (str(output_file_path), "")
            export_button.menu().actions()[0].trigger()

        with open(output_file_path, encoding="utf-8") as output_file:
            assert "Bien\nvenue dans" in output_file.read()
