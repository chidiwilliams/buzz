import os
import time
import pytest
import platform
import tempfile

from unittest.mock import patch
from pytestqt.qtbot import QtBot

from buzz.locale import _
from buzz.widgets.recording_transcriber_widget import RecordingTranscriberWidget
from buzz.settings.settings import Settings

from tests.mock_sounddevice import MockSoundDevice, MockInputStream


class TestRecordingTranscriberWidget:
    def test_should_set_window_title(self, qtbot: QtBot):
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)
            assert widget.windowTitle() == _("Live Recording")

            # Test will hang if we call close before mock_sounddevice thread has fully started.
            time.sleep(3)

            widget.close()

    @pytest.mark.skipif(
        platform.system() == "Darwin" and platform.mac_ver()[0].startswith('13.'),
        reason="Does not pick up mock sound device")
    def test_should_transcribe(self, qtbot):
        with (patch(
                  "buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                  return_value=16_000)):

            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            widget.device_sample_rate = 16_000
            qtbot.add_widget(widget)

            assert len(widget.transcription_text_box.toPlainText()) == 0

            def assert_text_box_contains_text():
                assert len(widget.transcription_text_box.toPlainText()) > 0

            widget.record_button.click()
            qtbot.wait_until(callback=assert_text_box_contains_text, timeout=60 * 1000)

            with qtbot.wait_signal(widget.transcription_thread.finished, timeout=60 * 1000):
                widget.stop_recording()

            assert len(widget.transcription_text_box.toPlainText()) > 0
            widget.close()

    @pytest.mark.skipif(
        platform.system() == "Darwin" and platform.mac_ver()[0].startswith('13.'),
        reason="Does not pick up mock sound device")
    def test_should_transcribe_and_export(self, qtbot):
        settings = Settings()
        settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FOLDER,
            tempfile.gettempdir(),
        )

        try:
            os.remove(os.path.join(tempfile.gettempdir(), 'mock-export-file.txt'))
        except FileNotFoundError:
            pass

        with (patch(
                  "buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                  return_value=16_000),
              patch(
                  'buzz.settings.settings.Settings.get_default_export_file_template',
                  return_value='mock-export-file')):

            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            widget.device_sample_rate = 16_000
            widget.export_enabled = True
            qtbot.add_widget(widget)

            assert len(widget.transcription_text_box.toPlainText()) == 0

            def assert_text_box_contains_text():
                assert len(widget.transcription_text_box.toPlainText()) > 0

            widget.record_button.click()
            qtbot.wait_until(callback=assert_text_box_contains_text, timeout=60 * 1000)

            with qtbot.wait_signal(widget.transcription_thread.finished, timeout=60 * 1000):
                widget.stop_recording()

            assert len(widget.transcription_text_box.toPlainText()) > 0

            with open(widget.transcript_export_file, 'r') as file:
                contents = file.read()
                assert len(contents) > 0

            widget.close()
