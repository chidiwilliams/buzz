import pathlib
import uuid

import pytest
from pytestqt.qtbot import QtBot

from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.export_transcription_menu import (
    ExportTranscriptionMenu,
)
from tests.audio import test_audio_path


class TestExportTranscriptionMenu:
    @pytest.fixture()
    def transcription(
        self, transcription_dao, transcription_segment_dao
    ) -> Transcription:
        id = uuid.uuid4()
        transcription_dao.insert(
            Transcription(
                id=str(id),
                status="completed",
                file=test_audio_path,
                task=Task.TRANSCRIBE.value,
                model_type=ModelType.WHISPER.value,
                whisper_model_size=WhisperModelSize.SMALL.value,
            )
        )
        transcription_segment_dao.insert(TranscriptionSegment(40, 299, "Bien", "", str(id)))
        transcription_segment_dao.insert(
            TranscriptionSegment(299, 329, "venue dans", "", str(id))
        )

        return transcription_dao.find_by_id(str(id))

    def test_should_export_segments(
        self,
        tmp_path: pathlib.Path,
        qtbot: QtBot,
        transcription,
        transcription_service,
        shortcuts,
        mocker,
    ):
        output_file_path = tmp_path / "whisper.txt"
        mocker.patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=(str(output_file_path), ""),
        )

        widget = ExportTranscriptionMenu(
            transcription,
            transcription_service,
        )
        qtbot.add_widget(widget)

        widget.actions()[0].trigger()

        with open(output_file_path, encoding="utf-8") as output_file:
            assert "Bien venue dans" in output_file.read()
