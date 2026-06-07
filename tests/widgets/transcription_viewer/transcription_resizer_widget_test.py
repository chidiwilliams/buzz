import uuid

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtSql import QSqlQuery

from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.transcription_resizer_widget import (
    TranscriptionResizerWidget,
)
from tests.audio import test_audio_path


class TestTranscriptionResizerWidgetCreateNewTranscript:
    """Tests for the "Create new transcript" preference."""

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
                word_level_timings=0,
            )
        )
        # Long segment so resize will split it into multiple subtitles.
        transcription_segment_dao.insert(
            TranscriptionSegment(
                0,
                5000,
                "This is a fairly long sentence that should be split into "
                "several smaller subtitle entries when resized.",
                "",
                str(id),
            )
        )
        return transcription_dao.find_by_id(str(id))

    @pytest.fixture(autouse=True)
    def _reset_setting(self):
        settings = Settings()
        settings.settings.remove(
            Settings.Key.TRANSCRIPTION_RESIZER_CREATE_NEW_TRANSCRIPT.value
        )
        yield
        settings.settings.remove(
            Settings.Key.TRANSCRIPTION_RESIZER_CREATE_NEW_TRANSCRIPT.value
        )

    def _transcription_count(self, dao) -> int:
        query = QSqlQuery("SELECT COUNT(*) FROM transcription", dao.db)
        query.next()
        return query.value(0)

    def _make_widget(self, qtbot, transcription, transcription_service):
        widget = TranscriptionResizerWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.add_widget(widget)
        return widget

    def test_checkbox_defaults_to_checked(
        self, qtbot: QtBot, transcription, transcription_service
    ):
        widget = self._make_widget(qtbot, transcription, transcription_service)

        assert widget.create_new_transcript_checkbox.isChecked()

    def test_toggling_checkbox_persists_to_settings(
        self, qtbot: QtBot, transcription, transcription_service
    ):
        widget = self._make_widget(qtbot, transcription, transcription_service)

        widget.create_new_transcript_checkbox.setChecked(False)

        settings = Settings()
        assert (
            settings.value(
                Settings.Key.TRANSCRIPTION_RESIZER_CREATE_NEW_TRANSCRIPT, True
            )
            is False
        )

    def test_checkbox_loads_state_from_settings(
        self, qtbot: QtBot, transcription, transcription_service
    ):
        settings = Settings()
        settings.set_value(
            Settings.Key.TRANSCRIPTION_RESIZER_CREATE_NEW_TRANSCRIPT, False
        )

        widget = self._make_widget(qtbot, transcription, transcription_service)

        assert not widget.create_new_transcript_checkbox.isChecked()

    def test_resize_creates_new_transcript_when_checked(
        self,
        qtbot: QtBot,
        transcription,
        transcription_service,
        transcription_dao,
    ):
        widget = self._make_widget(qtbot, transcription, transcription_service)
        widget.create_new_transcript_checkbox.setChecked(True)

        count_before = self._transcription_count(transcription_dao)

        widget.on_resize_button_clicked()

        assert self._transcription_count(transcription_dao) == count_before + 1

    def test_resize_updates_in_place_when_unchecked(
        self,
        qtbot: QtBot,
        transcription,
        transcription_service,
        transcription_dao,
    ):
        widget = self._make_widget(qtbot, transcription, transcription_service)
        widget.create_new_transcript_checkbox.setChecked(False)

        count_before = self._transcription_count(transcription_dao)

        widget.on_resize_button_clicked()

        # No new transcription created.
        assert self._transcription_count(transcription_dao) == count_before

        # Segments of the existing transcription were replaced (and split).
        segments = transcription_service.get_transcription_segments(
            transcription.id_as_uuid
        )
        assert len(segments) > 1
