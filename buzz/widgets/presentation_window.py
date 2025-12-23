import logging
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from platformdirs import user_cache_dir

from buzz.locale import _
from buzz.settings.settings import Settings

import os

class PresentationWindow(QWidget):
    """Window for displaying live transcripts in presentation mode"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.settings = Settings()
        self._current_transcript = ""
        self._current_translation = ""
        self.window_style = ""
        self.setWindowTitle(_("Live Transcript Presentation"))
        self.setWindowFlag(Qt.WindowType.Window)

        # Window size
        self.resize(800, 600)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Text display widget
        self.transcript_display = QTextBrowser(self)
        self.transcript_display.setReadOnly(True)

        # Translation display (hidden first)
        self.translation_display = QTextBrowser(self)
        self.translation_display.setReadOnly(True)
        self.translation_display.hide()

        # Add to layout
        layout.addWidget(self.transcript_display)
        layout.addWidget(self.translation_display)

        self.load_settings()

    def load_settings(self):
        """Load and apply saved presentation settings"""
        theme = self.settings.value(
            Settings.Key.PRESENTATION_WINDOW_THEME,
            "light"
        )

        # Load text size
        text_size = self.settings.value(
            Settings.Key.PRESENTATION_WINDOW_TEXT_SIZE,
            24,
            int
        )

        # Load colors based on theme
        if theme == "light":
            text_color = "#000000"
            bg_color = "#FFFFFF"
        elif theme == "dark":
            text_color = "#FFFFFF"
            bg_color = "#000000"
        else:
            text_color = self.settings.value(
                Settings.Key.PRESENTATION_WINDOW_TEXT_COLOR,
                "#000000"
            )

            bg_color = self.settings.value(
                Settings.Key.PRESENTATION_WINDOW_BACKGROUND_COLOR,
                "#FFFFFF"
            )

        self.apply_styling(text_color, bg_color, text_size)

        # Refresh content with new styling
        if self._current_transcript:
            self.update_transcripts(self._current_transcript)
        if self._current_translation:
            self.update_translations(self._current_translation)

    def apply_styling(self, text_color: str, bg_color: str, text_size: int):
        """Apply text color, background color and font size"""

        # Load custom CSS if it exists
        css_file_path = self.get_css_file_path()

        if os.path.exists(css_file_path):
            try:
                with open(css_file_path, "r", encoding="utf-8") as f:
                    self.window_style = f.read()
            except Exception as e:
                logging.warning(f"Failed to load custom CSS: {e}")
        else:
            self.window_style = f"""
                body {{
                    color: {text_color};
                    background-color: {bg_color};
                    font-size: {text_size}pt;
                    font-family: Arial, sans-serif;
                    padding: 0;
                    margin: 20px;
                }}
            """

    def update_transcripts(self, text: str):
        """Update the transcript display with new text"""
        if not text:
            return

        self._current_transcript = text
        escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html_text = escaped_text.replace("\n", "<br>")

        html_content = f"""
                    <html>
                        <head>
                            <style>
                                {self.window_style}
                            </style>
                        </head>
                        <body>
                            {html_text}
                        </body>
                    </html>
                    """

        self.transcript_display.setHtml(html_content)
        self.transcript_display.moveCursor(QTextCursor.MoveOperation.End)

    def update_translations(self, text: str):
        """Update the translation display with new text"""
        if not text:
            return

        self._current_translation = text
        self.translation_display.show()

        escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html_text = escaped_text.replace("\n", "<br>")

        html_content = f"""
                    <html>
                        <head>
                            <style>
                                {self.window_style}
                            </style>
                        </head>
                        <body>
                            {html_text}
                        </body>
                    </html>
                    """

        self.translation_display.setHtml(html_content)
        self.translation_display.moveCursor(QTextCursor.MoveOperation.End)

    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event):
        """Handle keyboard events"""
        # ESC Key exits fullscreen
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
            event.accept()
        else:
            super().keyPressEvent(event)


    def get_css_file_path(self) -> str:
        """Get path to custom CSS file"""
        cache_dir = user_cache_dir("Buzz")
        os.makedirs(cache_dir, exist_ok=True)

        return os.path.join(cache_dir, "presentation_window_style.css")


