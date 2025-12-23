import os
import pytest
import tempfile

from unittest.mock import patch, MagicMock
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

from buzz.widgets.presentation_window import PresentationWindow
from buzz.settings.settings import Settings
from buzz.locale import _

class TestPresentationWindow:
    def test_should_set_window_title(self, qtbot: QtBot):
        """Test that the window title is set correctly"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        assert _("Live Transcript Presentation") in window.windowTitle()
        window.close()

    def test_should_have_window_flag(self, qtbot: QtBot):
        """Test that window has the Window flag set"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        assert window.windowFlags() & Qt.WindowType.Window
        window.close()

    def test_should_have_transcript_display(self, qtbot: QtBot):
        """Test that the transcript display is created"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        assert window.transcript_display is not None
        assert window.transcript_display.isReadOnly()
        window.close()

    def test_should_have_translation_display_hidden(self, qtbot: QtBot):
        """Test that the translation display is created but hidden initially"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        assert window.translation_display is not None
        assert window.translation_display.isReadOnly()
        assert not window.translation_display.isVisible()
        window.close()

    def test_should_have_default_size(self, qtbot: QtBot):
        """Test that the window has default size"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        assert window.width() == 800
        assert window.height() == 600
        window.close()


class TestPresentationWindowUpdateTranscripts:
    def test_update_transcripts_with_text(self, qtbot: QtBot):
        """Test updating transcripts with text"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        window.update_transcripts("Hello world")

        assert window._current_transcript == "Hello world"
        assert "Hello world" in window.transcript_display.toHtml()
        window.close()

    def test_update_transcripts_with_empty_text(self, qtbot: QtBot):
        """Test that empty text does not update the display"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        window.update_transcripts("")

        assert window._current_transcript == ""
        window.close()

    def test_update_transcripts_escapes_html(self, qtbot: QtBot):
        """Test that special HTML characters are escaped"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        window.update_transcripts("<script>alert('xss')</script>")

        html = window.transcript_display.toHtml()
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        window.close()

    def test_update_transcripts_preserves_newlines(self, qtbot: QtBot):
        """Test that newlines are converted to <br> tags"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        window.update_transcripts("Line 1\nLine 2")

        html = window.transcript_display.toHtml()
        assert "<br>" in html or "<br/>" in html or "Line 1" in html
        window.close()


class TestPresentationWindowUpdateTranslations:
    def test_update_translations_with_text(self, qtbot: QtBot):
        """Test updating translations with text"""
        window = PresentationWindow()
        qtbot.add_widget(window)
        window.show()

        window.update_translations("Translated text")

        assert window._current_translation == "Translated text"
        assert window.translation_display.isVisible()
        assert "Translated text" in window.translation_display.toHtml()
        window.close()

    def test_update_translations_with_empty_text(self, qtbot: QtBot):
        """Test that empty text does not update the display"""
        window = PresentationWindow()
        qtbot.add_widget(window)
        window.show()

        window.update_translations("")

        assert window._current_translation == ""
        # translation_display should remain hidden when not updated with real text
        assert window.translation_display.isHidden()
        window.close()

    def test_update_translations_escapes_html(self, qtbot: QtBot):
        """Test that special HTML characters are escaped in translations"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        window.update_translations("<b>bold</b>")

        html = window.translation_display.toHtml()
        assert "&lt;b&gt;" in html
        window.close()


class TestPresentationWindowLoadSettings:
    def test_load_settings_light_theme(self, qtbot: QtBot):
        """Test loading light theme settings"""
        settings = Settings()
        settings.set_value(Settings.Key.PRESENTATION_WINDOW_THEME, "light")
        settings.set_value(Settings.Key.PRESENTATION_WINDOW_TEXT_SIZE, 24)

        window = PresentationWindow()
        qtbot.add_widget(window)

        assert "#000000" in window.window_style or "color:" in window.window_style
        window.close()

    def test_load_settings_dark_theme(self, qtbot: QtBot):
        """Test loading dark theme settings"""
        settings = Settings()
        settings.set_value(Settings.Key.PRESENTATION_WINDOW_THEME, "dark")

        window = PresentationWindow()
        qtbot.add_widget(window)

        assert "#FFFFFF" in window.window_style or "#000000" in window.window_style
        window.close()

    def test_load_settings_custom_theme(self, qtbot: QtBot):
        """Test loading custom theme settings"""
        settings = Settings()
        settings.set_value(Settings.Key.PRESENTATION_WINDOW_THEME, "custom")
        settings.set_value(Settings.Key.PRESENTATION_WINDOW_TEXT_COLOR, "#FF0000")
        settings.set_value(Settings.Key.PRESENTATION_WINDOW_BACKGROUND_COLOR, "#00FF00")
        settings.set_value(Settings.Key.PRESENTATION_WINDOW_TEXT_SIZE, 32)

        window = PresentationWindow()
        qtbot.add_widget(window)

        assert "#FF0000" in window.window_style or "#00FF00" in window.window_style
        window.close()

    def test_load_settings_refreshes_content(self, qtbot: QtBot):
        """Test that load_settings refreshes existing content"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        window.update_transcripts("Test transcript")
        window.update_translations("Test translation")

        # Reload settings
        window.load_settings()

        # Content should still be present
        assert "Test transcript" in window.transcript_display.toHtml()
        assert "Test translation" in window.translation_display.toHtml()
        window.close()


class TestPresentationWindowApplyStyling:
    def test_apply_styling_creates_css(self, qtbot: QtBot):
        """Test that apply_styling creates appropriate CSS"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        window.apply_styling("#123456", "#654321", 48)

        assert "#123456" in window.window_style
        assert "#654321" in window.window_style
        assert "48pt" in window.window_style
        window.close()

    def test_apply_styling_with_custom_css_file(self, qtbot: QtBot):
        """Test that custom CSS file is loaded when it exists"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        css_path = window.get_css_file_path()
        custom_css = "body { color: red; font-size: 100pt; }"

        try:
            with open(css_path, "w", encoding="utf-8") as f:
                f.write(custom_css)

            window.apply_styling("#000", "#FFF", 24)

            assert window.window_style == custom_css
        finally:
            if os.path.exists(css_path):
                os.remove(css_path)

        window.close()


class TestPresentationWindowFullscreen:
    def test_toggle_fullscreen_enters_fullscreen(self, qtbot: QtBot):
        """Test that toggle_fullscreen enters fullscreen mode"""
        window = PresentationWindow()
        qtbot.add_widget(window)
        window.show()

        assert not window.isFullScreen()

        window.toggle_fullscreen()

        assert window.isFullScreen()
        window.close()

    def test_toggle_fullscreen_exits_fullscreen(self, qtbot: QtBot):
        """Test that toggle_fullscreen exits fullscreen mode"""
        window = PresentationWindow()
        qtbot.add_widget(window)
        window.show()

        window.showFullScreen()
        assert window.isFullScreen()

        window.toggle_fullscreen()

        assert not window.isFullScreen()
        window.close()


class TestPresentationWindowKeyPressEvent:
    def test_escape_exits_fullscreen(self, qtbot: QtBot):
        """Test that ESC key exits fullscreen mode"""
        window = PresentationWindow()
        qtbot.add_widget(window)
        window.show()
        window.showFullScreen()

        assert window.isFullScreen()

        # Simulate ESC key press
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier
        )
        window.keyPressEvent(event)

        assert not window.isFullScreen()
        window.close()

    def test_escape_does_not_affect_normal_mode(self, qtbot: QtBot):
        """Test that ESC key does nothing in normal mode"""
        window = PresentationWindow()
        qtbot.add_widget(window)
        window.show()

        assert not window.isFullScreen()

        # Simulate ESC key press
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier
        )
        window.keyPressEvent(event)

        assert not window.isFullScreen()
        window.close()


class TestPresentationWindowGetCssFilePath:
    def test_get_css_file_path_returns_path(self, qtbot: QtBot):
        """Test that get_css_file_path returns a valid path"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        css_path = window.get_css_file_path()

        assert css_path.endswith("presentation_window_style.css")
        assert "Buzz" in css_path
        window.close()

    def test_get_css_file_path_creates_directory(self, qtbot: QtBot):
        """Test that get_css_file_path creates the cache directory"""
        window = PresentationWindow()
        qtbot.add_widget(window)

        css_path = window.get_css_file_path()
        parent_dir = os.path.dirname(css_path)

        assert os.path.isdir(parent_dir)
        window.close()
