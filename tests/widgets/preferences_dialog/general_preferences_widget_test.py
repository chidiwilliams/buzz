from PyQt6.QtWidgets import QPushButton, QMessageBox, QLineEdit

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

        assert test_button.text() == "Test"
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
            assert message_box_warning_mock.call_args[0][1] == "OpenAI API Key Test"
            assert (
                message_box_warning_mock.call_args[0][2]
                == "Incorrect API key provided: wrong-ap*-key. You can find your "
                "API key at https://platform.openai.com/account/api-keys."
            )

        qtbot.waitUntil(mock_called)
