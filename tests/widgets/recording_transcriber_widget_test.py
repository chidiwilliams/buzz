import os
import time
import pytest
import platform
import tempfile

from unittest.mock import patch, MagicMock
from pytestqt.qtbot import QtBot
from PyQt6.QtWidgets import QColorDialog
from PyQt6.QtGui import QColor

from buzz.locale import _
from buzz.settings.recording_transcriber_mode import RecordingTranscriberMode
from buzz.widgets.recording_transcriber_widget import RecordingTranscriberWidget
from buzz.widgets.presentation_window import PresentationWindow
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
                  return_value='mock-export-file'),
              patch("sounddevice.query_devices", side_effect=MockSoundDevice().query_devices),
              patch("sounddevice.check_input_settings", side_effect=MockSoundDevice().check_input_settings),
              patch("sounddevice.InputStream", side_effect=MockSoundDevice().InputStream)):

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

    @pytest.mark.timeout(60)
    def test_on_next_transcription_append_above(self, qtbot: QtBot):
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.transcriber_mode = RecordingTranscriberMode.APPEND_ABOVE

            widget.on_next_transcription('test1')
            assert widget.transcription_text_box.toPlainText() == 'test1\n\n'

            widget.on_next_transcription('test2')
            assert widget.transcription_text_box.toPlainText() == 'test2\n\ntest1\n\n'

            qtbot.wait(500)

            widget.close()

    def test_find_common_part_exact_match(self):
        assert RecordingTranscriberWidget.find_common_part("hello world", "hello world") == "hello world"

    def test_find_common_part_partial_match(self):
        assert (RecordingTranscriberWidget.find_common_part(
            "hello great and beautiful world",
            "hello great and beautiful butterfly")
                == "hello great and beautiful ")
        assert (RecordingTranscriberWidget.find_common_part(
            "Alice said hello world",
            "salad said hello world")
                == " said hello world")
        assert (RecordingTranscriberWidget.find_common_part(
            "To kauls nav paņemts no mājām. Ja varēsim rīt iet, es ļoti priecāšos. Mani uztrauc laikapstākļi.",
            "Kauls nav paņemts no mājām. Ja varēsim rīt iet, es ļoti priecāšos. Mani uztrauc laikapstākļi, tāpēc...")
                == "auls nav paņemts no mājām. Ja varēsim rīt iet, es ļoti priecāšos. Mani uztrauc laikapstākļi")

    def test_find_common_part_no_match(self):
        assert RecordingTranscriberWidget.find_common_part("hello world", "goodbye evil") == ""

    def test_find_common_part_different_start(self):
        assert RecordingTranscriberWidget.find_common_part("abc hello world", "xyz hello world") == " hello world"

    def test_find_common_part_empty_strings(self):
        assert RecordingTranscriberWidget.find_common_part("", "hello world") == ""
        assert RecordingTranscriberWidget.find_common_part("hello world", "") == ""
        assert RecordingTranscriberWidget.find_common_part("", "") == ""

    @pytest.mark.timeout(60)
    def test_on_next_transcription_append_and_correct(self, qtbot: QtBot):
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.transcriber_mode = RecordingTranscriberMode.APPEND_AND_CORRECT

            widget.on_next_transcription('Bienvenue dans la transcription en direct de Buzz.')
            assert widget.transcription_text_box.toPlainText() == 'Bienvenue dans la transcription en direct de Buzz.'

            widget.on_next_transcription('transcription en direct de Buzz. Ceci est la deuxième phrase.')
            assert widget.transcription_text_box.toPlainText() == 'Bienvenue dans la transcription en direct de Buzz. Ceci est la deuxième phrase.'

            widget.on_next_transcription('Ceci est la deuxième phrase. Et voici la troisième.')
            assert widget.transcription_text_box.toPlainText() == 'Bienvenue dans la transcription en direct de Buzz. Ceci est la deuxième phrase. Et voici la troisième.'

            qtbot.wait(500)

            widget.close()


class TestRecordingTranscriberWidgetPresentation:
    """Tests for presentation window related functionality"""

    @pytest.mark.timeout(60)
    def test_presentation_options_bar_created(self, qtbot: QtBot):
        """Test that presentation options bar is created"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            assert widget.presentation_options_bar is not None
            assert not widget.presentation_options_bar.isVisible()

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_presentation_options_bar_has_buttons(self, qtbot: QtBot):
        """Test that presentation options bar has all expected buttons"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            assert widget.show_presentation_button is not None
            assert widget.fullscreen_button is not None
            assert widget.text_size_spinbox is not None
            assert widget.theme_combo is not None
            assert widget.text_color_button is not None
            assert widget.bg_color_button is not None

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_presentation_window_initially_none(self, qtbot: QtBot):
        """Test that presentation window is None initially"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            assert widget.presentation_window is None

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_show_presentation_clicked_creates_window(self, qtbot: QtBot):
        """Test that clicking show presentation button creates the window"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.on_show_presentation_clicked()

            assert widget.presentation_window is not None
            assert isinstance(widget.presentation_window, PresentationWindow)
            assert widget.presentation_window.isVisible()
            assert widget.fullscreen_button.isEnabled()

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_show_presentation_clicked_syncs_content(self, qtbot: QtBot):
        """Test that clicking show presentation button syncs existing content"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            # Add some text to the transcription box
            widget.transcription_text_box.setPlainText("Test transcript text")

            widget.on_show_presentation_clicked()

            assert widget.presentation_window._current_transcript == "Test transcript text"

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_show_presentation_clicked_brings_existing_to_front(self, qtbot: QtBot):
        """Test that clicking show presentation button brings existing window to front"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            # Create window first
            widget.on_show_presentation_clicked()
            first_window = widget.presentation_window

            # Click again
            widget.on_show_presentation_clicked()

            # Should be the same window
            assert widget.presentation_window is first_window

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_text_size_changed(self, qtbot: QtBot):
        """Test that text size change updates settings"""
        settings = Settings()

        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.on_text_size_changed(36)

            # Wait for debounce
            qtbot.wait(200)

            saved_size = settings.value(Settings.Key.PRESENTATION_WINDOW_TEXT_SIZE, 24, int)
            assert saved_size == 36

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_theme_changed_light(self, qtbot: QtBot):
        """Test that theme change to light works"""
        settings = Settings()

        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.on_them_changed(0)  # light theme

            saved_theme = settings.value(Settings.Key.PRESENTATION_WINDOW_THEME, "")
            assert saved_theme == "light"
            # Color buttons should be hidden for light theme
            assert widget.text_color_button.isHidden()
            assert widget.bg_color_button.isHidden()

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_theme_changed_dark(self, qtbot: QtBot):
        """Test that theme change to dark works"""
        settings = Settings()

        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.on_them_changed(1)  # dark theme

            saved_theme = settings.value(Settings.Key.PRESENTATION_WINDOW_THEME, "")
            assert saved_theme == "dark"
            # Color buttons should be hidden for dark theme
            assert widget.text_color_button.isHidden()
            assert widget.bg_color_button.isHidden()

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_theme_changed_custom(self, qtbot: QtBot):
        """Test that theme change to custom shows color buttons"""
        settings = Settings()

        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.on_them_changed(2)  # custom theme

            saved_theme = settings.value(Settings.Key.PRESENTATION_WINDOW_THEME, "")
            assert saved_theme == "custom"
            # Color buttons should NOT be hidden for custom theme
            assert not widget.text_color_button.isHidden()
            assert not widget.bg_color_button.isHidden()

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_text_color_clicked(self, qtbot: QtBot):
        """Test that text color button opens color dialog and saves selection"""
        settings = Settings()

        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings"),
              patch.object(QColorDialog, 'getColor', return_value=QColor("#FF5500"))):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.on_text_color_clicked()

            saved_color = settings.value(Settings.Key.PRESENTATION_WINDOW_TEXT_COLOR, "")
            assert saved_color == "#ff5500"

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_text_color_clicked_cancel(self, qtbot: QtBot):
        """Test that cancelling color dialog does not save"""
        settings = Settings()
        original_color = settings.value(Settings.Key.PRESENTATION_WINDOW_TEXT_COLOR, "#000000")

        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings"),
              patch.object(QColorDialog, 'getColor', return_value=QColor())):  # Invalid color = cancelled
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.on_text_color_clicked()

            saved_color = settings.value(Settings.Key.PRESENTATION_WINDOW_TEXT_COLOR, "")
            assert saved_color == original_color

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_bg_color_clicked(self, qtbot: QtBot):
        """Test that background color button opens color dialog and saves selection"""
        settings = Settings()

        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings"),
              patch.object(QColorDialog, 'getColor', return_value=QColor("#00AA55"))):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.on_bg_color_clicked()

            saved_color = settings.value(Settings.Key.PRESENTATION_WINDOW_BACKGROUND_COLOR, "")
            assert saved_color == "#00aa55"

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_fullscreen_clicked(self, qtbot: QtBot):
        """Test that fullscreen button toggles presentation window fullscreen"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            # Create presentation window first
            widget.on_show_presentation_clicked()

            assert not widget.presentation_window.isFullScreen()

            widget.on_fullscreen_clicked()

            assert widget.presentation_window.isFullScreen()

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_fullscreen_clicked_without_window(self, qtbot: QtBot):
        """Test that fullscreen button does nothing without presentation window"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            # Should not raise exception
            widget.on_fullscreen_clicked()

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_presentation_window_updates_on_transcription(self, qtbot: QtBot):
        """Test that presentation window updates when new transcription arrives"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.on_show_presentation_clicked()

            widget.transcriber_mode = RecordingTranscriberMode.APPEND_BELOW
            widget.on_next_transcription("Hello world")

            assert "Hello world" in widget.presentation_window._current_transcript

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_close_event_closes_presentation_window(self, qtbot: QtBot):
        """Test that closing widget also closes presentation window"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.on_show_presentation_clicked()
            presentation_window = widget.presentation_window

            time.sleep(0.5)

            widget.close()

            assert widget.presentation_window is None

    @pytest.mark.timeout(60)
    def test_fullscreen_button_disabled_initially(self, qtbot: QtBot):
        """Test that fullscreen button is disabled when no presentation window"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            assert not widget.fullscreen_button.isEnabled()

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_presentation_bar_shown_when_recording(self, qtbot: QtBot):
        """Test that presentation bar is shown when recording starts"""
        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            widget.device_sample_rate = 16_000
            qtbot.add_widget(widget)

            # Initially hidden
            assert widget.presentation_options_bar.isHidden()

            # Click record button
            widget.record_button.click()

            # Should no longer be hidden after recording starts
            assert not widget.presentation_options_bar.isHidden()

            time.sleep(0.5)
            widget.close()
