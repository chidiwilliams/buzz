from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QMessageBox, QLineEdit, QCheckBox

from buzz.locale import _
from buzz.settings.settings import Settings
from buzz.widgets.preferences_dialog.general_preferences_widget import (
    GeneralPreferencesWidget,
)


class TestGeneralPreferencesWidget:
    def test_should_disable_test_button_if_no_api_key(self, qtbot, mocker):
        mocker.patch(
            "buzz.widgets.preferences_dialog.general_preferences_widget.get_password",
            return_value="",
        )

        widget = GeneralPreferencesWidget()
        qtbot.add_widget(widget)

        test_button = widget.findChild(QPushButton)
        assert isinstance(test_button, QPushButton)

        assert test_button.text() == _("Test")
        assert not test_button.isEnabled()

        line_edit = widget.findChild(QLineEdit)
        assert isinstance(line_edit, QLineEdit)
        line_edit.setText("123")

        assert test_button.isEnabled()

    def test_should_test_openai_api_key(self, qtbot, mocker):
        mocker.patch(
            "buzz.widgets.preferences_dialog.general_preferences_widget.get_password",
            return_value="wrong-api-key",
        )

        widget = GeneralPreferencesWidget()
        qtbot.add_widget(widget)

        test_button = widget.findChild(QPushButton)
        assert isinstance(test_button, QPushButton)

        test_button.click()

        message_box_warning_mock = mocker.Mock()
        QMessageBox.warning = message_box_warning_mock

        def mock_called():
            message_box_warning_mock.assert_called()
            assert message_box_warning_mock.call_args[0][1] == _("OpenAI API Key Test")
            assert (
                    message_box_warning_mock.call_args[0][2]
                    == "Incorrect API key provided: wrong-ap*-key. You can find your "
                       "API key at https://platform.openai.com/account/api-keys."
            )

        qtbot.waitUntil(mock_called)

    def test_recording_export_preferences(self, qtbot, mocker):
        mocker.patch(
            "PyQt6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value="/path/to/export/folder",
        )

        widget = GeneralPreferencesWidget()
        qtbot.add_widget(widget)

        browse_button = widget.findChild(QPushButton, "RecordingExportFolderBrowseButton")
        checkbox = widget.findChild(QCheckBox, "EnableRecordingExportCheckbox")

        browse_button_enabled = browse_button.isEnabled()

        qtbot.mouseClick(widget.export_enabled_checkbox, Qt.MouseButton.LeftButton)
        checkbox.setChecked(not browse_button_enabled)

        assert browse_button.isEnabled() != browse_button_enabled

        qtbot.mouseClick(widget.recording_export_folder_browse_button, Qt.MouseButton.LeftButton)

        assert widget.recording_export_folder_line_edit.text() == "/path/to/export/folder"

        assert widget.settings.value(
            key=widget.settings.Key.RECORDING_TRANSCRIBER_EXPORT_ENABLED,
            default_value=False) != browse_button_enabled
        assert widget.settings.value(
            key=widget.settings.Key.RECORDING_TRANSCRIBER_EXPORT_FOLDER,
            default_value='/home/user/documents') == '/path/to/export/folder'

    def test_openai_base_url_preferences(self, qtbot, mocker):
        widget = GeneralPreferencesWidget()
        qtbot.add_widget(widget)

        settings = Settings()

        openai_base_url = settings.value(
            key=Settings.Key.CUSTOM_OPENAI_BASE_URL, default_value=""
        )

        assert openai_base_url == ""
        assert widget.custom_openai_base_url_line_edit.text() == ""

        widget.custom_openai_base_url_line_edit.setText("http://localhost:11434/v1")

        updated_openai_base_url = settings.value(
            key=Settings.Key.CUSTOM_OPENAI_BASE_URL, default_value=""
        )

        assert updated_openai_base_url == "http://localhost:11434/v1"
