from unittest.mock import Mock

from PyQt6.QtWidgets import QPushButton, QMessageBox, QLineEdit

from buzz.store.keyring_store import KeyringStore
from buzz.widgets.preferences_dialog.general_preferences_widget import (
    GeneralPreferencesWidget,
)


class TestGeneralPreferencesWidget:
    def test_should_disable_test_button_if_no_api_key(self, qtbot):
        widget = GeneralPreferencesWidget(
            keyring_store=self.get_keyring_store(""), default_export_file_name=""
        )
        qtbot.add_widget(widget)

        test_button = widget.findChild(QPushButton)
        assert isinstance(test_button, QPushButton)

        assert test_button.text() == "Test"
        assert not test_button.isEnabled()

        line_edit = widget.findChild(QLineEdit)
        assert isinstance(line_edit, QLineEdit)
        line_edit.setText("123")

        assert test_button.isEnabled()

    def test_should_test_openai_api_key(self, qtbot):
        widget = GeneralPreferencesWidget(
            keyring_store=self.get_keyring_store("wrong-api-key"),
            default_export_file_name="",
        )
        qtbot.add_widget(widget)

        test_button = widget.findChild(QPushButton)
        assert isinstance(test_button, QPushButton)

        test_button.click()

        mock = Mock()
        QMessageBox.warning = mock

        def mock_called():
            mock.assert_called()
            assert mock.call_args[0][1] == "OpenAI API Key Test"
            assert (
                mock.call_args[0][2]
                == "Incorrect API key provided: wrong-ap*-key. You can find your API key at https://platform.openai.com/account/api-keys."
            )

        qtbot.waitUntil(mock_called)

    @staticmethod
    def get_keyring_store(password: str):
        keyring_store = Mock(KeyringStore)
        keyring_store.get_password.return_value = password
        return keyring_store
