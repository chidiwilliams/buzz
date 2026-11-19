from unittest.mock import Mock, patch

import pytest

from PyQt6.QtCore import Qt
from pytestqt.qtbot import QtBot

from buzz.model_loader import ModelType, TranscriptionModel
from buzz.transcriber.transcriber import TranscriptionOptions
from buzz.widgets.transcriber.file_transcriber_widget import FileTranscriberWidget
from buzz.widgets.transcriber.speaker_identification_options_widget import (
    SpeakerIdentificationOptions,
    SpeakerIdentificationOptionsWidget,
    is_speaker_identification_available,
)
from tests.audio import test_audio_path


class TestFileTranscriberWidget:
    def test_should_set_window_title(self, qtbot: QtBot):
        widget = FileTranscriberWidget(
            file_paths=[test_audio_path],
        )
        qtbot.add_widget(widget)
        assert widget.windowTitle() == "whisper-french.mp3"

    def test_should_emit_triggered_event(self, qtbot: QtBot):
        widget = FileTranscriberWidget(
            file_paths=[test_audio_path],
        )
        qtbot.add_widget(widget)

        mock_triggered = Mock()
        widget.triggered.connect(mock_triggered)

        with qtbot.wait_signal(widget.triggered, timeout=30 * 1000):
            qtbot.mouseClick(widget.run_button, Qt.MouseButton.LeftButton)

        (
            transcription_options,
            file_transcription_options,
            model_path,
            speaker_identification_options,
        ) = mock_triggered.call_args[0][0]
        assert transcription_options.language is None
        assert file_transcription_options.file_paths == [test_audio_path]
        assert len(model_path) > 0
        assert isinstance(speaker_identification_options, SpeakerIdentificationOptions)

    @pytest.mark.skipif(
        not is_speaker_identification_available(),
        reason="Speaker identification is not available on Intel Macs",
    )
    def test_speaker_identification_options_are_emitted_and_remembered(
        self, qtbot: QtBot
    ):
        widget = FileTranscriberWidget(file_paths=[test_audio_path])
        qtbot.add_widget(widget)

        options_widget = widget.findChild(
            SpeakerIdentificationOptionsWidget
        )
        options_widget.identify_speakers_checkbox.setChecked(True)
        options_widget.speaker_count_combo_box.setCurrentIndex(
            options_widget.speaker_count_combo_box.findData(3)
        )
        options_widget.merge_speaker_sentences_checkbox.setChecked(False)

        mock_triggered = Mock()
        widget.triggered.connect(mock_triggered)
        widget.on_model_loaded("/path/to/model")

        assert mock_triggered.call_args[0][0][3] == SpeakerIdentificationOptions(
            identify_speakers=True,
            speaker_diarizer="msdd",
            speaker_count=3,
            merge_speaker_sentences=False,
        )

        # The dialog was closed, so the choice is shown the next time
        reopened = FileTranscriberWidget(file_paths=[test_audio_path])
        qtbot.add_widget(reopened)
        reopened_options = reopened.findChild(SpeakerIdentificationOptionsWidget)
        assert reopened_options.identify_speakers_checkbox.isChecked()
        assert reopened_options.speaker_count_combo_box.currentData() == 3

        reopened_options.identify_speakers_checkbox.setChecked(False)
        reopened.close()

    def test_speaker_identification_is_hidden_when_unavailable(self, qtbot: QtBot):
        with patch(
            "buzz.widgets.transcriber.file_transcriber_widget.is_speaker_identification_available",
            return_value=False,
        ):
            widget = FileTranscriberWidget(file_paths=[test_audio_path])
        qtbot.add_widget(widget)

        assert widget.findChild(SpeakerIdentificationOptionsWidget) is None

        mock_triggered = Mock()
        widget.triggered.connect(mock_triggered)
        widget.on_model_loaded("/path/to/model")

        assert mock_triggered.call_args[0][0][3].identify_speakers is False

    def test_on_model_loaded_empty_path_shows_error_for_local_model(self, qtbot: QtBot):
        widget = FileTranscriberWidget(file_paths=[test_audio_path])
        qtbot.add_widget(widget)
        widget.transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.FASTER_WHISPER)
        )

        mock_triggered = Mock()
        widget.triggered.connect(mock_triggered)

        with patch("buzz.widgets.transcriber.file_transcriber_widget.show_model_download_error_dialog") as mock_err, \
             patch.object(widget, "save_preferences"):
            widget.on_model_loaded("")
            mock_err.assert_called_once()
            mock_triggered.assert_not_called()

    def test_on_model_loaded_empty_path_allowed_for_openai_api(self, qtbot: QtBot):
        widget = FileTranscriberWidget(file_paths=[test_audio_path])
        qtbot.add_widget(widget)
        widget.transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API)
        )

        mock_triggered = Mock()
        widget.triggered.connect(mock_triggered)

        with patch("buzz.widgets.transcriber.file_transcriber_widget.show_model_download_error_dialog") as mock_err, \
             patch.object(widget, "save_preferences"):
            widget.on_model_loaded("")
            mock_err.assert_not_called()
            mock_triggered.assert_called_once()
