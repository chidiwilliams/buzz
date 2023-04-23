from unittest.mock import Mock

from PyQt6.QtWidgets import QPushButton, QMessageBox

from buzz.widgets.general_preferences_widget import GeneralPreferencesWidget


class TestGeneralPreferencesWidget:
    def test_should_disable_test_button_if_no_api_key(self, qtbot):
        widget = GeneralPreferencesWidget(openai_api_key='')
        qtbot.add_widget(widget)

        test_button = widget.findChild(QPushButton)
        assert isinstance(test_button, QPushButton)

        assert test_button.text() == 'Test'
        assert not test_button.isEnabled()

    def test_should_test_openai_api_key(self, qtbot):
        widget = GeneralPreferencesWidget(openai_api_key='wrong-api-key')
        qtbot.add_widget(widget)

        test_button = widget.findChild(QPushButton)
        assert isinstance(test_button, QPushButton)

        test_button.click()

        mock = Mock()
        QMessageBox.warning = mock

        def mock_called():
            mock.assert_called()
            assert mock.call_args[0][1] == 'OpenAI API Key Test'
            assert mock.call_args[0][
                       2] == 'Incorrect API key provided: wrong-ap*-key. You can find your API key at https://platform.openai.com/account/api-keys.'

        qtbot.waitUntil(mock_called)
