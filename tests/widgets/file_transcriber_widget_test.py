from unittest.mock import Mock

from PyQt6.QtCore import Qt
from pytestqt.qtbot import QtBot

from buzz.widgets.transcriber.file_transcriber_widget import FileTranscriberWidget
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
        ) = mock_triggered.call_args[0][0]
        assert transcription_options.language is None
        assert file_transcription_options.file_paths == [test_audio_path]
        assert len(model_path) > 0
