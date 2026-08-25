import logging
import random
import string
import uuid
from unittest.mock import Mock, patch

import pytest
from pytestqt.qtbot import QtBot

from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)
from tests.audio import test_audio_path


class TestTranscriptionViewerTranslation:
    """Translation flow of the transcription viewer, with the LLM API mocked out"""

    @pytest.fixture()
    def transcription(self, transcription_dao, transcription_segment_dao) -> Transcription:
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
        transcription_segment_dao.insert(
            TranscriptionSegment(40, 500, "First segment", "", str(id))
        )
        transcription_segment_dao.insert(
            TranscriptionSegment(500, 1000, "Second segment", "", str(id))
        )

        return transcription_dao.find_by_id(str(id))

    @pytest.fixture()
    def viewer_settings(self):
        """Isolated settings so the test starts with no saved translation
        preferences and does not write into the real Buzz settings"""
        application = "".join(
            random.choice(string.ascii_letters + string.digits) for _ in range(6)
        )
        settings = Settings(application=application)
        # QSettings falls back to the organization wide file when a key is
        # missing, so write the empty defaults explicitly to shadow whatever
        # the machine running the tests has saved
        settings.settings.beginGroup("file_transcriber")
        settings.settings.setValue("enable_llm_translation", False)
        settings.settings.setValue("llm_model", "")
        settings.settings.setValue("llm_prompt", "")
        settings.settings.endGroup()
        with patch.object(TranscriptionViewerWidget, "settings", settings):
            yield settings
        settings.clear()

    @pytest.fixture()
    def openai_client(self):
        """Mocked OpenAI client, no LLM is ever called"""
        with patch("buzz.translator.OpenAI") as mock_openai, patch(
            "buzz.translator.get_password", return_value="test-api-key"
        ), patch(
            "buzz.widgets.transcription_viewer.transcription_viewer_widget.get_password",
            return_value="test-api-key",
        ):
            mock_openai.return_value.chat.completions.create.return_value = Mock(
                choices=[
                    Mock(message=Mock(content="[1] Pirmais\n[2] Otrais"))
                ]
            )
            yield mock_openai.return_value

    def open_viewer(self, qtbot, transcription, transcription_service, shortcuts):
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)
        return widget

    def test_translate_button_opens_settings_and_starts_translation(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts,
        viewer_settings, openai_client
    ):
        """Pressing Translate opens the settings dialog, accepting it translates.

        The user only fills in the AI model, the instructions for the AI are
        left at the value the dialog pre-fills for them.
        """
        widget = self.open_viewer(
            qtbot, transcription, transcription_service, shortcuts)

        assert widget.transcription_options.llm_model == ""

        widget.on_translate_button_clicked()

        dialog = widget.transcription_options_dialog
        assert dialog.isVisible()

        dialog.llm_model_line_edit.setText("llama3")

        translations = []
        widget.translator.translation.connect(
            lambda text, segment_id: translations.append((text, segment_id))
        )

        dialog.accept()

        qtbot.wait_until(lambda: len(translations) == 2, timeout=10 * 1000)
        assert all(text for text, _ in translations)

        create = openai_client.chat.completions.create
        assert create.called

        # The prompt shown pre-filled in the dialog has to be the one actually
        # sent, an empty prompt used to silently abort the whole translation
        llm_prompt = widget.transcription_options.llm_prompt
        assert llm_prompt != ""
        system_message = create.call_args.kwargs["messages"][0]["content"]
        assert llm_prompt in system_message
        assert create.call_args.kwargs["model"] == "llama3"

        widget.close()

    def test_translate_button_opens_settings_when_already_configured(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts,
        viewer_settings, openai_client
    ):
        """The settings dialog opens on every press, also once settings are saved"""
        widget = self.open_viewer(
            qtbot, transcription, transcription_service, shortcuts)

        widget.transcription_options.llm_model = "llama3"
        widget.transcription_options.llm_prompt = "Translate this:"

        widget.on_translate_button_clicked()

        assert widget.transcription_options_dialog.isVisible()
        assert openai_client.chat.completions.create.call_count == 0

        widget.close()

    def test_rejecting_settings_does_not_translate(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts,
        viewer_settings, openai_client
    ):
        widget = self.open_viewer(
            qtbot, transcription, transcription_service, shortcuts)

        widget.on_translate_button_clicked()
        widget.transcription_options_dialog.llm_model_line_edit.setText("llama3")
        widget.transcription_options_dialog.reject()

        qtbot.wait(200)

        assert openai_client.chat.completions.create.call_count == 0
        assert widget.translator.queue.empty()

        widget.close()

    def test_repeated_presses_enqueue_segments_once(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts,
        viewer_settings, openai_client
    ):
        """Pressing Translate twice before accepting must not translate twice"""
        widget = self.open_viewer(
            qtbot, transcription, transcription_service, shortcuts)

        with patch.object(widget.translator, "enqueue") as enqueue:
            widget.on_translate_button_clicked()
            widget.on_translate_button_clicked()
            widget.transcription_options_dialog.llm_model_line_edit.setText("llama3")
            widget.transcription_options_dialog.accept()

            assert enqueue.call_count == 2  # one per segment, not two per segment

        widget.close()

    def test_missing_model_logs_warning_and_does_not_translate(
        self, qtbot: QtBot, caplog, transcription, transcription_service,
        shortcuts, viewer_settings, openai_client
    ):
        """Accepting the dialog without an AI model warns instead of failing silently"""
        widget = self.open_viewer(
            qtbot, transcription, transcription_service, shortcuts)

        widget.on_translate_button_clicked()

        with caplog.at_level(logging.WARNING):
            widget.transcription_options_dialog.accept()

        assert any(
            record.levelno == logging.WARNING
            and "Translation not started" in record.message
            for record in caplog.records
        )
        assert openai_client.chat.completions.create.call_count == 0
        assert widget.translator.queue.empty()

        widget.close()

    def test_translation_settings_are_saved(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts,
        viewer_settings, openai_client
    ):
        """Settings entered for a translation are there on the next open"""
        widget = self.open_viewer(
            qtbot, transcription, transcription_service, shortcuts)

        widget.on_translate_button_clicked()
        widget.transcription_options_dialog.llm_model_line_edit.setText("llama3")
        widget.transcription_options_dialog.accept()
        widget.close()

        next_widget = self.open_viewer(
            qtbot, transcription, transcription_service, shortcuts)

        assert next_widget.transcription_options.llm_model == "llama3"
        assert next_widget.transcription_options.llm_prompt != ""

        next_widget.close()
