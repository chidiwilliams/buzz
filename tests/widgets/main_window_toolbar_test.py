from unittest.mock import patch

from PyQt6.QtCore import Qt
from pytestqt.qtbot import QtBot

from buzz.widgets.main_window_toolbar import MainWindowToolbar


class TestMainWindowToolbar:
    def test_record_window_is_deleted_on_close(self, qtbot: QtBot, shortcuts):
        toolbar = MainWindowToolbar(shortcuts=shortcuts, parent=None)
        qtbot.add_widget(toolbar)

        with patch(
            "buzz.widgets.recording_transcriber_widget.RecordingTranscriberWidget"
        ) as mock_widget_class:
            toolbar.on_record_action_triggered()

        window = mock_widget_class.return_value
        window.setAttribute.assert_called_once_with(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.show.assert_called_once()
