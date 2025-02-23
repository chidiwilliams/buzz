import multiprocessing
import platform
from unittest.mock import Mock, patch

import pytest
import sounddevice
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QValidator, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QMessageBox,
)
from pytestqt.qtbot import QtBot

from buzz.locale import _
from buzz.__version__ import VERSION
from buzz.widgets.audio_devices_combo_box import AudioDevicesComboBox
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog
from buzz.widgets.transcriber.hugging_face_search_line_edit import (
    HuggingFaceSearchLineEdit,
)
from buzz.widgets.transcriber.languages_combo_box import LanguagesComboBox
from buzz.widgets.transcriber.temperature_validator import TemperatureValidator
from buzz.widgets.about_dialog import AboutDialog
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import (
    TranscriptionOptions,
)
from buzz.widgets.transcriber.transcription_options_group_box import (
    TranscriptionOptionsGroupBox,
)
from tests.mock_sounddevice import MockInputStream, mock_query_devices
from .mock_qt import MockNetworkAccessManager, MockNetworkReply

if platform.system() == "Linux":
    multiprocessing.set_start_method("spawn")


@pytest.fixture(scope="module", autouse=True)
def audio_setup():
    with patch("sounddevice.query_devices") as query_devices_mock, patch(
        "sounddevice.InputStream", side_effect=MockInputStream
    ), patch("sounddevice.check_input_settings"):
        query_devices_mock.return_value = mock_query_devices
        sounddevice.default.device = 3, 4
        yield


class TestLanguagesComboBox:
    def test_should_show_sorted_whisper_languages(self, qtbot):
        languages_combox_box = LanguagesComboBox("en")
        qtbot.add_widget(languages_combox_box)
        assert languages_combox_box.itemText(0) == _("Detect Language")
        assert languages_combox_box.itemText(1) == _("Afrikaans")

    def test_should_select_en_as_default_language(self, qtbot):
        languages_combox_box = LanguagesComboBox("en")
        qtbot.add_widget(languages_combox_box)
        assert languages_combox_box.currentText() == _("English")

    def test_should_select_detect_language_as_default(self, qtbot):
        languages_combo_box = LanguagesComboBox(None)
        qtbot.add_widget(languages_combo_box)
        assert languages_combo_box.currentText() == _("Detect Language")


class TestAudioDevicesComboBox:
    def test_get_devices(self):
        audio_devices_combo_box = AudioDevicesComboBox()

        assert audio_devices_combo_box.itemText(0) == "Background Music"
        assert audio_devices_combo_box.itemText(1) == "Background Music (UI Sounds)"
        assert audio_devices_combo_box.itemText(2) == "BlackHole 2ch"
        assert audio_devices_combo_box.itemText(3) == "MacBook Pro Microphone"
        assert audio_devices_combo_box.itemText(4) == "Null Audio Device"

        assert audio_devices_combo_box.currentText() == "MacBook Pro Microphone"

    def test_select_default_mic_when_no_default(self):
        sounddevice.default.device = -1, 1

        audio_devices_combo_box = AudioDevicesComboBox()
        assert audio_devices_combo_box.currentText() == "Background Music"


@pytest.fixture(scope="module", autouse=True)
def clear_settings():
    settings = Settings()
    settings.clear()


class TestAboutDialog:
    def test_should_check_for_updates(self, qtbot: QtBot):
        reply = MockNetworkReply(data={"name": "v" + VERSION})
        manager = MockNetworkAccessManager(reply=reply)
        dialog = AboutDialog(network_access_manager=manager)
        qtbot.add_widget(dialog)

        mock_message_box_information = Mock()
        QMessageBox.information = mock_message_box_information

        with qtbot.wait_signal(dialog.network_access_manager.finished):
            dialog.check_updates_button.click()

        mock_message_box_information.assert_called_with(
            dialog, "", _("You're up to date!")
        )


class TestAdvancedSettingsDialog:
    def test_should_update_advanced_settings(self, qtbot: QtBot):
        dialog = AdvancedSettingsDialog(
            transcription_options=TranscriptionOptions(
                temperature=(0.0, 0.8),
                initial_prompt="prompt",
                enable_llm_translation=False,
                llm_model="",
                llm_prompt=""
            )
        )
        qtbot.add_widget(dialog)

        transcription_options_mock = Mock()
        dialog.transcription_options_changed.connect(transcription_options_mock)

        assert dialog.windowTitle() == _("Advanced Settings")
        assert dialog.temperature_line_edit.text() == "0.0, 0.8"
        assert dialog.initial_prompt_text_edit.toPlainText() == "prompt"
        assert dialog.enable_llm_translation_checkbox.isChecked() is False
        assert dialog.llm_model_line_edit.text() == ""
        assert dialog.llm_prompt_text_edit.toPlainText() == ""

        dialog.temperature_line_edit.setText("0.0, 0.8, 1.0")
        dialog.initial_prompt_text_edit.setPlainText("new prompt")
        dialog.enable_llm_translation_checkbox.setChecked(True)
        dialog.llm_model_line_edit.setText("model")
        dialog.llm_prompt_text_edit.setPlainText("Please translate this text")

        assert transcription_options_mock.call_args[0][0].temperature == (0.0, 0.8, 1.0)
        assert transcription_options_mock.call_args[0][0].initial_prompt == "new prompt"
        assert transcription_options_mock.call_args[0][0].enable_llm_translation is True
        assert transcription_options_mock.call_args[0][0].llm_model == "model"
        assert transcription_options_mock.call_args[0][0].llm_prompt == "Please translate this text"


class TestTemperatureValidator:
    validator = TemperatureValidator(None)

    @pytest.mark.parametrize(
        "text,state",
        [
            ("0.0,0.5,1.0", QValidator.State.Acceptable),
            ("0.0,0.5,", QValidator.State.Intermediate),
            ("0.0,0.5,p", QValidator.State.Invalid),
        ],
    )
    def test_should_validate_temperature(self, text: str, state: QValidator.State):
        assert self.validator.validate(text, 0)[0] == state


class TestHuggingFaceSearchLineEdit:
    def test_should_update_selected_model_on_type(self, qtbot: QtBot):
        widget = HuggingFaceSearchLineEdit(
            default_value="",
            network_access_manager=self.network_access_manager()
        )
        qtbot.add_widget(widget)

        mock_model_selected = Mock()
        widget.model_selected.connect(mock_model_selected)

        self._set_text_and_wait_response(qtbot, widget)
        mock_model_selected.assert_called_with("openai/whisper-tiny")

    def test_should_show_list_of_models(self, qtbot: QtBot):
        widget = HuggingFaceSearchLineEdit(
            default_value="",
            network_access_manager=self.network_access_manager()
        )
        qtbot.add_widget(widget)

        self._set_text_and_wait_response(qtbot, widget)

        assert widget.popup.count() > 0
        assert "openai/whisper-tiny" in widget.popup.item(0).text()

    def test_should_select_model_from_list(self, qtbot: QtBot):
        widget = HuggingFaceSearchLineEdit(
            default_value="",
            network_access_manager=self.network_access_manager()
        )
        qtbot.add_widget(widget)

        mock_model_selected = Mock()
        widget.model_selected.connect(mock_model_selected)

        self._set_text_and_wait_response(qtbot, widget)

        # press down arrow and enter to select next item
        QApplication.sendEvent(
            widget.popup,
            QKeyEvent(
                QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier
            ),
        )
        QApplication.sendEvent(
            widget.popup,
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Enter,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

        mock_model_selected.assert_called_with("openai/whisper-tiny.en")

    @staticmethod
    def network_access_manager():
        reply = MockNetworkReply(
            data=[{"id": "openai/whisper-tiny"}, {"id": "openai/whisper-tiny.en"}]
        )
        return MockNetworkAccessManager(reply=reply)

    @staticmethod
    def _set_text_and_wait_response(qtbot: QtBot, widget: HuggingFaceSearchLineEdit):
        with qtbot.wait_signal(widget.network_manager.finished):
            widget.setText("openai/whisper-tiny")
            widget.textEdited.emit("openai/whisper-tiny")


class TestTranscriptionOptionsGroupBox:
    def test_should_update_model_type(self, qtbot):
        widget = TranscriptionOptionsGroupBox()
        qtbot.add_widget(widget)

        mock_transcription_options_changed = Mock()
        widget.transcription_options_changed.connect(mock_transcription_options_changed)

        widget.model_type_combo_box.setCurrentIndex(1)

        mock_transcription_options_changed.assert_called()
