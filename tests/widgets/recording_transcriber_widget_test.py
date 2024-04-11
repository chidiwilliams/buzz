from pytestqt.qtbot import QtBot

from buzz.widgets.recording_transcriber_widget import RecordingTranscriberWidget
import pytest


class TestRecordingTranscriberWidget:
    def test_should_set_window_title(self, qtbot: QtBot):
        widget = RecordingTranscriberWidget()
        qtbot.add_widget(widget)
        assert widget.windowTitle() == "Live Recording"
        widget.close()

    @pytest.mark.skip(reason="Seg faults on CI")
    def test_should_transcribe(self, qtbot):
        widget = RecordingTranscriberWidget()
        qtbot.add_widget(widget)

        def assert_text_box_contains_text():
            assert len(widget.text_box.toPlainText()) > 0

        widget.record_button.click()
        qtbot.wait_until(callback=assert_text_box_contains_text, timeout=60 * 1000)

        with qtbot.wait_signal(widget.transcription_thread.finished, timeout=60 * 1000):
            widget.stop_recording()

        assert "Welcome to Passe" in widget.text_box.toPlainText()
        widget.close()
