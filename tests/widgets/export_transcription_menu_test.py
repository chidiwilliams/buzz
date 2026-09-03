import pathlib
import uuid
import zipfile
from unittest.mock import Mock
from xml.etree import ElementTree

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from pytestqt.qtbot import QtBot

from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.export_transcription_menu import (
    ExportTranscriptionMenu,
)
from tests.audio import test_audio_path


class TranslationSignal(QObject):
    translation = pyqtSignal(str, int)


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
                whisper_model_size=WhisperModelSize.TINY.value,
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

        translation_signal = TranslationSignal()

        widget = ExportTranscriptionMenu(
            transcription,
            transcription_service,
            False,
            translation_signal.translation
        )
        qtbot.add_widget(widget)

        widget.actions()[0].trigger()

        with open(output_file_path, encoding="utf-8") as output_file:
            assert "Bien venue dans" in output_file.read()

    def test_should_include_structured_speaker_in_export(
        self,
        tmp_path: pathlib.Path,
        qtbot: QtBot,
        transcription,
        transcription_service,
        mocker,
    ):
        segments = transcription_service.get_transcription_segments(
            transcription.id_as_uuid
        )
        transcription_service.update_segment_speaker(segments[0].id, "Nyomi")
        output_file_path = tmp_path / "speakers.txt"
        mocker.patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=(str(output_file_path), ""),
        )
        translation_signal = TranslationSignal()
        widget = ExportTranscriptionMenu(
            transcription,
            transcription_service,
            False,
            translation_signal.translation,
        )
        qtbot.add_widget(widget)

        widget.actions()[0].trigger()

        assert output_file_path.read_text(encoding="utf-8").startswith(
            "Nyomi: Bien"
        )

    def test_should_export_colored_speaker_docx_with_optional_timestamps(
        self,
        tmp_path: pathlib.Path,
        qtbot: QtBot,
        transcription,
        transcription_service,
        mocker,
    ):
        segments = transcription_service.get_transcription_segments(
            transcription.id_as_uuid
        )
        transcription_service.update_segment_speaker(segments[0].id, "Nyomi")
        transcription_service.update_segment_speaker(
            segments[1].id,
            "Mediator",
        )
        output_file_path = tmp_path / "hearing.docx"
        mocker.patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=(str(output_file_path), ""),
        )
        mocker.patch(
            "PyQt6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        )
        translation_signal = TranslationSignal()
        widget = ExportTranscriptionMenu(
            transcription,
            transcription_service,
            False,
            translation_signal.translation,
        )
        qtbot.add_widget(widget)

        assert widget.speaker_docx_action.isEnabled()
        widget.speaker_docx_action.trigger()

        with zipfile.ZipFile(output_file_path) as docx:
            document = docx.read("word/document.xml").decode("utf-8")

        ElementTree.fromstring(document)
        assert "Nyomi" in document
        assert "Mediator" in document
        assert 'w:color w:val="1976D2"' in document
        assert 'w:color w:val="C62828"' in document
        assert "[00:00:00.040 – 00:00:00.299]" in document

    def test_speaker_docx_export_is_disabled_without_assigned_speakers(
        self,
        qtbot: QtBot,
        transcription,
        transcription_service,
    ):
        translation_signal = TranslationSignal()
        widget = ExportTranscriptionMenu(
            transcription,
            transcription_service,
            False,
            translation_signal.translation,
        )
        qtbot.add_widget(widget)

        assert not widget.speaker_docx_action.isEnabled()

    def test_speaker_docx_default_path_sanitizes_name(
        self,
        tmp_path: pathlib.Path,
        qtbot: QtBot,
        monkeypatch,
    ):
        title = "中文 | test?."
        transcription = Transcription(
            file=str(tmp_path / "audio.wav"),
            name=title,
        )
        transcription_service = Mock()
        transcription_service.get_transcription_segments.return_value = [
            Mock(speaker="Speaker")
        ]
        get_save_file_name = Mock(return_value=("", ""))
        monkeypatch.setattr(QFileDialog, "getSaveFileName", get_save_file_name)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            Mock(return_value=QMessageBox.StandardButton.No),
        )
        translation_signal = TranslationSignal()
        widget = ExportTranscriptionMenu(
            transcription,
            transcription_service,
            False,
            translation_signal.translation,
        )
        qtbot.add_widget(widget)

        widget.export_speakers_docx()

        default_path = get_save_file_name.call_args.args[2]
        assert transcription.name == title
        assert pathlib.Path(default_path).name == "中文 _ test_#_speakers.docx"
