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


class TestRecordingTranscriberWidgetLineSeparator:
    @pytest.mark.timeout(60)
    def test_line_separator_loaded_from_settings(self, qtbot: QtBot):
        settings = Settings()
        settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_LINE_SEPARATOR, "\n")

        with _widget_ctx(qtbot) as widget:
            assert widget.transcription_options.line_separator == "\n"

    @pytest.mark.timeout(60)
    def test_line_separator_saved_on_close(self, qtbot: QtBot):
        settings = Settings()

        with _widget_ctx(qtbot) as widget:
            widget.transcription_options.line_separator = " | "

        assert settings.value(Settings.Key.RECORDING_TRANSCRIBER_LINE_SEPARATOR, "") == " | "

    @pytest.mark.timeout(60)
    def test_line_separator_used_in_append_below(self, qtbot: QtBot):
        with _widget_ctx(qtbot) as widget:
            widget.transcription_options.line_separator = " | "
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_BELOW
            widget.on_next_transcription("first")
            widget.on_next_transcription("second")
            assert widget.transcription_text_box.toPlainText() == "first | second"

    @pytest.mark.timeout(60)
    def test_line_separator_used_in_append_above(self, qtbot: QtBot):
        with _widget_ctx(qtbot) as widget:
            widget.transcription_options.line_separator = " | "
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_ABOVE
            widget.on_next_transcription("first")
            widget.on_next_transcription("second")
            assert widget.transcription_text_box.toPlainText() == "second | first | "

    @pytest.mark.timeout(60)
    def test_line_separator_used_in_translation_append_below(self, qtbot: QtBot):
        with _widget_ctx(qtbot) as widget:
            widget.transcription_options.line_separator = " | "
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_BELOW
            widget.on_next_translation("hello")
            widget.on_next_translation("world")
            assert widget.translation_text_box.toPlainText() == "hello | world"


class TestRecordingTranscriberWidgetSilenceThreshold:
    @pytest.mark.timeout(60)
    def test_silence_threshold_loaded_from_settings(self, qtbot: QtBot):
        """Silence threshold from settings is applied to transcription options."""
        settings = Settings()
        settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_SILENCE_THRESHOLD, 0.007)

        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(custom_sounddevice=MockSoundDevice())
            qtbot.add_widget(widget)

            assert widget.transcription_options.silence_threshold == pytest.approx(0.007)

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_silence_threshold_saved_on_close(self, qtbot: QtBot):
        """Silence threshold is persisted to settings when widget is closed."""
        settings = Settings()

        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                    return_value=16_000),
              patch("sounddevice.check_input_settings")):
            widget = RecordingTranscriberWidget(custom_sounddevice=MockSoundDevice())
            qtbot.add_widget(widget)

            widget.transcription_options.silence_threshold = 0.009
            time.sleep(0.5)
            widget.close()

        saved = settings.value(Settings.Key.RECORDING_TRANSCRIBER_SILENCE_THRESHOLD, 0.0)
        assert pytest.approx(float(saved)) == 0.009


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

            widget.on_theme_changed(0)  # light theme

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

            widget.on_theme_changed(1)  # dark theme

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

            widget.on_theme_changed(2)  # custom theme

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
              patch("buzz.widgets.recording_transcriber_widget.QColorDialog.getColor",
                    return_value=QColor("#FF5500"))):
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
              patch("buzz.widgets.recording_transcriber_widget.QColorDialog.getColor",
                    return_value=QColor())):  # Invalid color = cancelled
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
    def test_on_copy_transcript_clicked_with_text(self, qtbot: QtBot):
        with (
            patch("sounddevice.InputStream", side_effect=MockInputStream),
            patch("sounddevice.check_input_settings"),
            patch(
                "buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                return_value=16_000,
            ),
        ):
            mock_clipboard = MagicMock()
            mock_app = MagicMock()
            mock_app.clipboard.return_value = mock_clipboard

            widget = RecordingTranscriberWidget(custom_sounddevice=MockSoundDevice())
            qtbot.add_widget(widget)

            widget.transcription_text_box.setPlainText("Hello world")
            widget.copy_actions_bar.show()

            with patch("buzz.widgets.recording_transcriber_widget.QApplication.instance",
                        return_value=mock_app):
                widget.on_copy_transcript_clicked()

            mock_clipboard.setText.assert_called_once_with("Hello world")
            assert widget.copy_transcript_button.text() == _("Copied!")

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_on_copy_transcript_clicked_without_text(self, qtbot: QtBot):
        """Test that copy button handles empty transcript gracefully"""
        with (
            patch("sounddevice.InputStream", side_effect=MockInputStream),
            patch("sounddevice.check_input_settings"),
            patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                return_value=16_000),
        ):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            qtbot.add_widget(widget)

            widget.transcription_text_box.setPlainText("")
            widget.copy_actions_bar.show()

            widget.on_copy_transcript_clicked()

            assert widget.copy_transcript_button.text() == _("Nothing to copy!")

            time.sleep(0.5)
            widget.close()

    @pytest.mark.timeout(60)
    def test_copy_actions_bar_hidden_when_recording_starts(self, qtbot: QtBot):
        """Test that copy actions bar hides when recording starts"""
        with (
            patch("sounddevice.InputStream", side_effect=MockInputStream),
            patch("sounddevice.check_input_settings"),
            patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                return_value=16_000),
        ):
            widget = RecordingTranscriberWidget(
                custom_sounddevice=MockSoundDevice()
            )
            widget.device_sample_rate = 16_000
            qtbot.add_widget(widget)

            widget.copy_actions_bar.show()
            assert not widget.copy_actions_bar.isHidden()

            # Mock start_recording to prevent actual recording threads from starting
            widget.current_status = widget.RecordingStatus.STOPPED
            with patch.object(widget, 'start_recording'):
                widget.on_record_button_clicked()

            assert widget.copy_actions_bar.isHidden()

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
              patch("buzz.widgets.recording_transcriber_widget.QColorDialog.getColor",
                    return_value=QColor("#00AA55"))):
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

            # Simulate clicking record by directly calling the handler
            # This avoids starting actual recording threads
            widget.current_status = widget.RecordingStatus.RECORDING
            widget.record_button.set_recording()
            widget.transcription_options_group_box.setEnabled(False)
            widget.audio_devices_combo_box.setEnabled(False)
            widget.presentation_options_bar.show()

            # Should no longer be hidden after recording starts
            assert not widget.presentation_options_bar.isHidden()

            time.sleep(0.5)
            widget.close()

import contextlib

@contextlib.contextmanager
def _widget_ctx(qtbot):
    with (patch("sounddevice.InputStream", side_effect=MockInputStream),
          patch("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                return_value=16_000),
          patch("sounddevice.check_input_settings")):
        widget = RecordingTranscriberWidget(custom_sounddevice=MockSoundDevice())
        qtbot.add_widget(widget)
        yield widget
        time.sleep(0.3)
        widget.close()


class TestResetTranscriberControls:
    @pytest.mark.timeout(60)
    def test_record_button_disabled_for_faster_whisper_custom_without_hf_model(self, qtbot):
        from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
        from buzz.transcriber.transcriber import TranscriptionOptions

        with _widget_ctx(qtbot) as widget:
            widget.transcription_options = TranscriptionOptions(
                model=TranscriptionModel(
                    model_type=ModelType.FASTER_WHISPER,
                    whisper_model_size=WhisperModelSize.CUSTOM,
                    hugging_face_model_id="",
                )
            )
            widget.reset_transcriber_controls()
            assert not widget.record_button.isEnabled()

    @pytest.mark.timeout(60)
    def test_record_button_disabled_for_hugging_face_without_model_id(self, qtbot):
        from buzz.model_loader import TranscriptionModel, ModelType
        from buzz.transcriber.transcriber import TranscriptionOptions

        with _widget_ctx(qtbot) as widget:
            widget.transcription_options = TranscriptionOptions(
                model=TranscriptionModel(
                    model_type=ModelType.HUGGING_FACE,
                    hugging_face_model_id="",
                )
            )
            widget.reset_transcriber_controls()
            assert not widget.record_button.isEnabled()

    @pytest.mark.timeout(60)
    def test_record_button_enabled_for_hugging_face_with_model_id(self, qtbot):
        from buzz.model_loader import TranscriptionModel, ModelType
        from buzz.transcriber.transcriber import TranscriptionOptions

        with _widget_ctx(qtbot) as widget:
            widget.transcription_options = TranscriptionOptions(
                model=TranscriptionModel(
                    model_type=ModelType.HUGGING_FACE,
                    hugging_face_model_id="org/model",
                )
            )
            widget.reset_transcriber_controls()
            assert widget.record_button.isEnabled()



class TestOnTranscriptionOptionsChanged:
    @pytest.mark.timeout(60)
    def test_shows_translation_box_when_llm_enabled(self, qtbot):
        from buzz.transcriber.transcriber import TranscriptionOptions

        with _widget_ctx(qtbot) as widget:
            options = TranscriptionOptions(enable_llm_translation=True)
            widget.on_transcription_options_changed(options)
            assert not widget.translation_text_box.isHidden()

    @pytest.mark.timeout(60)
    def test_hides_translation_box_when_llm_disabled(self, qtbot):
        from buzz.transcriber.transcriber import TranscriptionOptions

        with _widget_ctx(qtbot) as widget:
            widget.translation_text_box.show()
            options = TranscriptionOptions(enable_llm_translation=False)
            widget.on_transcription_options_changed(options)
            assert widget.translation_text_box.isHidden()

    @pytest.mark.timeout(60)
    def test_updates_transcription_options(self, qtbot):
        from buzz.transcriber.transcriber import TranscriptionOptions

        with _widget_ctx(qtbot) as widget:
            options = TranscriptionOptions(silence_threshold=0.05)
            widget.on_transcription_options_changed(options)
            assert widget.transcription_options.silence_threshold == pytest.approx(0.05)



def _model_loaded_ctx(qtbot, enable_llm_translation=False):
    from buzz.transcriber.transcriber import TranscriptionOptions
    ctx = _widget_ctx(qtbot)
    widget = ctx.__enter__.__self__ if hasattr(ctx, '__enter__') else None

    class _Ctx:
        def __enter__(self_inner):
            self_inner.widget = ctx.__enter__()
            self_inner.widget.transcription_options = TranscriptionOptions(
                enable_llm_translation=enable_llm_translation
            )
            return self_inner.widget

        def __exit__(self_inner, *args):
            return ctx.__exit__(*args)

    return _Ctx()


class TestTranslatorSetup:
    @pytest.mark.timeout(60)
    def test_translator_created_when_llm_enabled(self, qtbot):
        with _model_loaded_ctx(qtbot, enable_llm_translation=True) as widget, \
                patch("buzz.widgets.recording_transcriber_widget.Translator") as MockTranslator, \
                patch("buzz.widgets.recording_transcriber_widget.RecordingTranscriber"), \
                patch("buzz.widgets.recording_transcriber_widget.QThread"):
            widget.on_model_loaded("/fake/model/path")
            MockTranslator.assert_called_once()

    @pytest.mark.timeout(60)
    def test_translator_not_created_when_llm_disabled(self, qtbot):
        with _model_loaded_ctx(qtbot, enable_llm_translation=False) as widget, \
                patch("buzz.widgets.recording_transcriber_widget.Translator") as MockTranslator, \
                patch("buzz.widgets.recording_transcriber_widget.RecordingTranscriber"), \
                patch("buzz.widgets.recording_transcriber_widget.QThread"):
            widget.on_model_loaded("/fake/model/path")
            MockTranslator.assert_not_called()

    @pytest.mark.timeout(60)
    def test_translator_translation_signal_connected_to_on_next_translation(self, qtbot):
        with _model_loaded_ctx(qtbot, enable_llm_translation=True) as widget, \
                patch("buzz.widgets.recording_transcriber_widget.Translator") as MockTranslator, \
                patch("buzz.widgets.recording_transcriber_widget.RecordingTranscriber"), \
                patch("buzz.widgets.recording_transcriber_widget.QThread"):
            mock_translator_instance = MagicMock()
            MockTranslator.return_value = mock_translator_instance
            widget.on_model_loaded("/fake/model/path")
            mock_translator_instance.translation.connect.assert_called_with(widget.on_next_translation)


class TestOnDeviceChanged:
    @pytest.mark.timeout(60)
    def test_no_new_listener_started_when_device_is_none(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            with patch("buzz.widgets.recording_transcriber_widget.RecordingAmplitudeListener") as MockListener:
                widget.on_device_changed(None)
                MockListener.assert_not_called()

    @pytest.mark.timeout(60)
    def test_no_new_listener_started_when_device_is_minus_one(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            with patch("buzz.widgets.recording_transcriber_widget.RecordingAmplitudeListener") as MockListener:
                widget.on_device_changed(-1)
                MockListener.assert_not_called()

    @pytest.mark.timeout(60)
    def test_device_id_updated(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            widget.on_device_changed(-1)
            assert widget.selected_device_id == -1



class TestOnRecordButtonClickedStop:
    @pytest.mark.timeout(60)
    def test_stop_path_sets_status_stopped(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            widget.current_status = widget.RecordingStatus.RECORDING
            with patch.object(widget, "stop_recording"), \
                 patch.object(widget, "set_recording_status_stopped") as mock_stop:
                widget.on_record_button_clicked()
                mock_stop.assert_called_once()

    @pytest.mark.timeout(60)
    def test_stop_path_hides_presentation_bar(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            widget.presentation_options_bar.show()
            widget.current_status = widget.RecordingStatus.RECORDING
            with patch.object(widget, "stop_recording"):
                widget.on_record_button_clicked()
            assert widget.presentation_options_bar.isHidden()



class TestOnModelLoaded:
    @pytest.mark.timeout(60)
    def test_empty_model_path_calls_transcriber_error(self, qtbot):
        from buzz.model_loader import TranscriptionModel, ModelType
        from buzz.transcriber.transcriber import TranscriptionOptions

        with _widget_ctx(qtbot) as widget:
            widget.transcription_options = TranscriptionOptions(
                model=TranscriptionModel(model_type=ModelType.FASTER_WHISPER)
            )
            with patch.object(widget, "on_transcriber_error") as mock_err, \
                 patch.object(widget, "reset_recording_controls"):
                widget.on_model_loaded("")
                mock_err.assert_called_once_with("")



class TestOnTranscriberError:
    @pytest.mark.timeout(60)
    def test_shows_message_box(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            with patch("buzz.widgets.recording_transcriber_widget.QMessageBox.critical") as mock_box, \
                 patch.object(widget, "reset_record_button"), \
                 patch.object(widget, "set_recording_status_stopped"), \
                 patch.object(widget, "reset_recording_amplitude_listener"):
                widget.on_transcriber_error("some error")
                mock_box.assert_called_once()

    @pytest.mark.timeout(60)
    def test_resets_record_button(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            with patch("buzz.widgets.recording_transcriber_widget.QMessageBox.critical"), \
                 patch.object(widget, "set_recording_status_stopped"), \
                 patch.object(widget, "reset_recording_amplitude_listener"):
                widget.on_transcriber_error("err")
                assert widget.record_button.isEnabled()



class TestOnCancelModelProgressDialog:
    @pytest.mark.timeout(60)
    def test_cancels_model_loader(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            mock_loader = MagicMock()
            widget.model_loader = mock_loader
            with patch.object(widget, "reset_model_download"), \
                 patch.object(widget, "set_recording_status_stopped"), \
                 patch.object(widget, "reset_recording_amplitude_listener"):
                widget.on_cancel_model_progress_dialog()
            mock_loader.cancel.assert_called_once()

    @pytest.mark.timeout(60)
    def test_record_button_re_enabled(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            widget.record_button.setDisabled(True)
            widget.model_loader = None
            with patch.object(widget, "reset_model_download"), \
                 patch.object(widget, "set_recording_status_stopped"), \
                 patch.object(widget, "reset_recording_amplitude_listener"):
                widget.on_cancel_model_progress_dialog()
            assert widget.record_button.isEnabled()



class TestOnNextTranscriptionExport:
    @pytest.mark.timeout(60)
    def test_append_below_writes_to_export_file(self, qtbot):
        with _widget_ctx(qtbot) as widget, tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False, mode="w"
        ) as f:
            export_path = f.name

        try:
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_BELOW
            widget.export_enabled = True
            widget.transcript_export_file = export_path
            widget.on_next_transcription("hello export")

            with open(export_path) as f:
                assert "hello export" in f.read()
        finally:
            os.unlink(export_path)

    @pytest.mark.timeout(60)
    def test_append_above_writes_to_export_file(self, qtbot):
        with _widget_ctx(qtbot) as widget, tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False, mode="w"
        ) as f:
            export_path = f.name

        try:
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_ABOVE
            widget.export_enabled = True
            widget.transcript_export_file = export_path
            widget.on_next_transcription("first")
            widget.on_next_transcription("second")

            with open(export_path) as f:
                content = f.read()
            assert "second" in content
            assert "first" in content
            # APPEND_ABOVE puts newer text first
            assert content.index("second") < content.index("first")
        finally:
            os.unlink(export_path)

    @pytest.mark.timeout(60)
    def test_append_above_csv_prepends_new_column(self, qtbot):
        import csv
        with _widget_ctx(qtbot) as widget, tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False, mode="w"
        ) as f:
            export_path = f.name

        try:
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_ABOVE
            widget.export_enabled = True
            widget.transcript_export_file = export_path
            widget.settings.set_value(
                Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_TYPE, "csv"
            )
            widget.on_next_transcription("first")
            widget.on_next_transcription("second")

            with open(export_path, newline="") as f:
                rows = [r for r in csv.reader(f) if r]
            assert len(rows) == 1
            assert rows[0][0] == "second"
            assert rows[0][1] == "first"
        finally:
            os.unlink(export_path)

    @pytest.mark.timeout(60)
    def test_append_above_csv_respects_max_entries(self, qtbot):
        import csv
        with _widget_ctx(qtbot) as widget, tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False, mode="w"
        ) as f:
            export_path = f.name

        try:
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_ABOVE
            widget.export_enabled = True
            widget.transcript_export_file = export_path
            widget.settings.set_value(
                Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_TYPE, "csv"
            )
            widget.settings.set_value(
                Settings.Key.RECORDING_TRANSCRIBER_EXPORT_MAX_ENTRIES, 2
            )
            widget.on_next_transcription("first")
            widget.on_next_transcription("second")
            widget.on_next_transcription("third")

            with open(export_path, newline="") as f:
                rows = [r for r in csv.reader(f) if r]
            assert len(rows) == 1
            assert len(rows[0]) == 2
            assert rows[0][0] == "third"
            assert rows[0][1] == "second"
        finally:
            os.unlink(export_path)



class TestUploadToServer:
    @pytest.mark.timeout(60)
    def test_transcript_uploaded_when_upload_url_set(self, qtbot):
        with _widget_ctx(qtbot) as widget, \
                patch("buzz.widgets.recording_transcriber_widget.requests.post") as mock_post:
            widget.upload_url = "http://example.com/upload"
            widget.on_next_transcription("hello upload")
            mock_post.assert_called_once_with(
                url="http://example.com/upload",
                json={"kind": "transcript", "text": "hello upload"},
                headers={"Content-Type": "application/json"},
                timeout=15,
            )

    @pytest.mark.timeout(60)
    def test_transcript_not_uploaded_when_upload_url_empty(self, qtbot):
        with _widget_ctx(qtbot) as widget, \
                patch("buzz.widgets.recording_transcriber_widget.requests.post") as mock_post:
            widget.upload_url = ""
            widget.on_next_transcription("no upload")
            mock_post.assert_not_called()

    @pytest.mark.timeout(60)
    def test_transcript_upload_failure_does_not_raise(self, qtbot):
        with _widget_ctx(qtbot) as widget, \
                patch("buzz.widgets.recording_transcriber_widget.requests.post",
                      side_effect=Exception("connection error")):
            widget.upload_url = "http://example.com/upload"
            widget.on_next_transcription("hello")  # should not raise

    @pytest.mark.timeout(60)
    def test_translation_uploaded_when_upload_url_set(self, qtbot):
        with _widget_ctx(qtbot) as widget, \
                patch("buzz.widgets.recording_transcriber_widget.requests.post") as mock_post:
            widget.upload_url = "http://example.com/upload"
            widget.on_next_translation("bonjour")
            mock_post.assert_called_once_with(
                url="http://example.com/upload",
                json={"kind": "translation", "text": "bonjour"},
                headers={"Content-Type": "application/json"},
                timeout=15,
            )


class TestOnNextTranslation:
    @pytest.mark.timeout(60)
    def test_append_below_adds_translation(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_BELOW
            widget.on_next_translation("Bonjour")
            assert "Bonjour" in widget.translation_text_box.toPlainText()

    @pytest.mark.timeout(60)
    def test_append_above_puts_new_text_first(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_ABOVE
            widget.on_next_translation("first")
            widget.on_next_translation("second")
            text = widget.translation_text_box.toPlainText()
            assert text.index("second") < text.index("first")

    @pytest.mark.timeout(60)
    def test_append_and_correct_merges_translation(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_AND_CORRECT
            widget.on_next_translation("Hello world.")
            widget.on_next_translation("world. Goodbye.")
            text = widget.translation_text_box.toPlainText()
            assert "Hello" in text
            assert "Goodbye" in text

    @pytest.mark.timeout(60)
    def test_empty_translation_ignored(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_BELOW
            widget.on_next_translation("")
            assert widget.translation_text_box.toPlainText() == ""

    @pytest.mark.timeout(60)
    def test_updates_presentation_window(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            widget.transcriber_mode = RecordingTranscriberMode.APPEND_BELOW
            widget.on_show_presentation_clicked()
            widget.transcription_options.enable_llm_translation = True
            widget.on_next_translation("Translated text")
            assert "Translated text" in widget.presentation_window._current_translation



class TestExportFileHelpers:
    def test_write_creates_file(self, tmp_path):
        path = str(tmp_path / "out.txt")
        RecordingTranscriberWidget.write_to_export_file(path, "hello")
        with open(path) as f:
            assert f.read() == "hello"

    def test_write_appends_by_default(self, tmp_path):
        path = str(tmp_path / "out.txt")
        RecordingTranscriberWidget.write_to_export_file(path, "line1")
        RecordingTranscriberWidget.write_to_export_file(path, "line2")
        with open(path) as f:
            assert f.read() == "line1line2"

    def test_write_overwrites_with_mode_w(self, tmp_path):
        path = str(tmp_path / "out.txt")
        RecordingTranscriberWidget.write_to_export_file(path, "old", mode="w")
        RecordingTranscriberWidget.write_to_export_file(path, "new", mode="w")
        with open(path) as f:
            assert f.read() == "new"

    def test_write_retries_on_permission_error(self, tmp_path):
        path = str(tmp_path / "out.txt")
        call_count = [0]
        original_open = open

        def flaky_open(p, mode="r", **kwargs):
            if p == path:
                call_count[0] += 1
                if call_count[0] < 3:
                    raise PermissionError("locked")
            return original_open(p, mode, **kwargs)

        with patch("builtins.open", side_effect=flaky_open), \
             patch("time.sleep"):
            RecordingTranscriberWidget.write_to_export_file(path, "data", retries=5, delay=0)

        assert call_count[0] == 3

    def test_write_gives_up_after_max_retries(self, tmp_path):
        path = str(tmp_path / "out.txt")
        with patch("builtins.open", side_effect=PermissionError("locked")), \
             patch("time.sleep"):
            RecordingTranscriberWidget.write_to_export_file(path, "data", retries=3, delay=0)

    def test_write_handles_oserror(self, tmp_path):
        path = str(tmp_path / "out.txt")
        with patch("builtins.open", side_effect=OSError("disk full")):
            RecordingTranscriberWidget.write_to_export_file(path, "data")

    def test_read_returns_file_contents(self, tmp_path):
        path = str(tmp_path / "in.txt")
        with open(path, "w") as f:
            f.write("content")
        assert RecordingTranscriberWidget.read_export_file(path) == "content"

    def test_read_retries_on_permission_error(self, tmp_path):
        path = str(tmp_path / "in.txt")
        with open(path, "w") as f:
            f.write("ok")
        call_count = [0]
        original_open = open

        def flaky_open(p, mode="r", **kwargs):
            if p == path:
                call_count[0] += 1
                if call_count[0] < 2:
                    raise PermissionError("locked")
            return original_open(p, mode, **kwargs)

        with patch("builtins.open", side_effect=flaky_open), \
             patch("time.sleep"):
            result = RecordingTranscriberWidget.read_export_file(path, retries=5, delay=0)

        assert result == "ok"

    def test_read_returns_empty_string_on_oserror(self, tmp_path):
        path = str(tmp_path / "missing.txt")
        with patch("builtins.open", side_effect=OSError("not found")):
            assert RecordingTranscriberWidget.read_export_file(path) == ""

    def test_read_returns_empty_string_after_max_retries(self, tmp_path):
        path = str(tmp_path / "locked.txt")
        with patch("builtins.open", side_effect=PermissionError("locked")), \
             patch("time.sleep"):
            result = RecordingTranscriberWidget.read_export_file(path, retries=2, delay=0)
        assert result == ""


class TestWriteCsvExport:
    def test_creates_csv_with_single_entry(self, tmp_path):
        path = str(tmp_path / "out.csv")
        RecordingTranscriberWidget.write_csv_export(path, "hello", 0)
        with open(path, encoding="utf-8-sig") as f:
            content = f.read()
        assert "hello" in content

    def test_appends_column_to_existing_csv(self, tmp_path):
        import csv
        path = str(tmp_path / "out.csv")
        RecordingTranscriberWidget.write_csv_export(path, "first", 0)
        RecordingTranscriberWidget.write_csv_export(path, "second", 0)
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        assert rows[0] == ["first", "second"]

    def test_max_entries_limits_columns(self, tmp_path):
        import csv
        path = str(tmp_path / "out.csv")
        for word in ["a", "b", "c", "d"]:
            RecordingTranscriberWidget.write_csv_export(path, word, max_entries=3)
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        assert rows[0] == ["b", "c", "d"]

    def test_max_entries_zero_means_no_limit(self, tmp_path):
        import csv
        path = str(tmp_path / "out.csv")
        for i in range(10):
            RecordingTranscriberWidget.write_csv_export(path, str(i), max_entries=0)
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        assert len(rows[0]) == 10

    def test_handles_empty_existing_file(self, tmp_path):
        import csv
        path = str(tmp_path / "out.csv")
        with open(path, "w") as f:
            f.write("")
        RecordingTranscriberWidget.write_csv_export(path, "entry", 0)
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        assert rows[0] == ["entry"]

    def test_retries_on_permission_error(self, tmp_path):
        path = str(tmp_path / "out.csv")
        call_count = [0]
        original_open = open

        def flaky_open(p, mode="r", **kwargs):
            if p == path and "w" in mode:
                call_count[0] += 1
                if call_count[0] < 3:
                    raise PermissionError("locked")
            return original_open(p, mode, **kwargs)

        with patch("builtins.open", side_effect=flaky_open), \
             patch("time.sleep"):
            RecordingTranscriberWidget.write_csv_export(path, "data", 0)

        assert call_count[0] == 3


class TestWriteTxtExport:
    def test_append_mode_adds_text(self, tmp_path):
        path = str(tmp_path / "out.txt")
        RecordingTranscriberWidget.write_txt_export(path, "line1", "a", 0, "\n")
        RecordingTranscriberWidget.write_txt_export(path, "line2", "a", 0, "\n")
        with open(path) as f:
            content = f.read()
        assert content == "line1\nline2\n"

    def test_append_mode_max_entries_trims_oldest(self, tmp_path):
        path = str(tmp_path / "out.txt")
        for word in ["a", "b", "c", "d"]:
            RecordingTranscriberWidget.write_txt_export(path, word, "a", max_entries=3, line_separator="\n")
        with open(path) as f:
            content = f.read()
        parts = [p for p in content.split("\n") if p]
        assert parts == ["b", "c", "d"]

    def test_prepend_mode_puts_text_first(self, tmp_path):
        path = str(tmp_path / "out.txt")
        RecordingTranscriberWidget.write_txt_export(path, "first", "a", 0, "\n")
        RecordingTranscriberWidget.write_txt_export(path, "second", "prepend", 0, "\n")
        with open(path) as f:
            content = f.read()
        parts = [p for p in content.split("\n") if p]
        assert parts[0] == "second"
        assert parts[1] == "first"

    def test_prepend_mode_max_entries_trims_oldest(self, tmp_path):
        path = str(tmp_path / "out.txt")
        RecordingTranscriberWidget.write_txt_export(path, "old1", "a", 0, "\n")
        RecordingTranscriberWidget.write_txt_export(path, "old2", "a", 0, "\n")
        RecordingTranscriberWidget.write_txt_export(path, "new", "prepend", max_entries=2, line_separator="\n")
        with open(path) as f:
            content = f.read()
        parts = [p for p in content.split("\n") if p]
        assert parts == ["new", "old1"]

    def test_write_mode_overwrites(self, tmp_path):
        path = str(tmp_path / "out.txt")
        RecordingTranscriberWidget.write_txt_export(path, "old", "w", 0, "\n")
        RecordingTranscriberWidget.write_txt_export(path, "new", "w", 0, "\n")
        with open(path) as f:
            content = f.read()
        assert content == "new"

    def test_prepend_on_nonexistent_file(self, tmp_path):
        path = str(tmp_path / "out.txt")
        RecordingTranscriberWidget.write_txt_export(path, "only", "prepend", 0, "\n")
        with open(path) as f:
            content = f.read()
        assert "only" in content

    def test_append_max_entries_zero_means_no_limit(self, tmp_path):
        path = str(tmp_path / "out.txt")
        for i in range(10):
            RecordingTranscriberWidget.write_txt_export(path, str(i), "a", max_entries=0, line_separator="\n")
        with open(path) as f:
            parts = [p for p in f.read().split("\n") if p]
        assert len(parts) == 10


class TestPresentationTranslationSync:
    @pytest.mark.timeout(60)
    def test_syncs_translation_when_llm_enabled(self, qtbot):
        with _widget_ctx(qtbot) as widget:
            widget.transcription_options.enable_llm_translation = True
            widget.translation_text_box.setPlainText("Translated content")
            widget.on_show_presentation_clicked()
            assert "Translated content" in widget.presentation_window._current_translation
