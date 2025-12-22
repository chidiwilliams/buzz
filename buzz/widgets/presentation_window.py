from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextBrowser

from buzz.locale import _
from buzz.settings.settings import Settings

class PresentationWindow(QWidget):
    """Window for displaying live transcripts in presentation mode"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.settings = Settings()
        self.setWindowTitle(_("Live Transcript Presentation"))
        self.setWindowFlag(Qt.WindowType.Window)

        # Window size
        self.resize(800, 600)

        #Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        #Text display widget
        self.transcript_display = QTextBrowser(self)
        self.transcript_display.setReadOnly(True)

        #Translation display (hidden first)
        self.translation_display = QTextBrowser(self)
        self.translation_display.setReadOnly(True)
        self.translation_display.hide()

        #Add to layout
        layout.addWidget(self.transcript_display)
        layout.addWidget(self.translation_display)

        self.load_settings()


    def load_settings(self):
        """Load and apply saved presentation settings"""
        theme = self.settings.value(
            Settings.Key.PRESENTATION_WINDOW_THEME,
            "light"
        )

        #Load text size
        text_size = self.settings.value(
            Settings.Key.PRESENTATION_WINDOW_TEXT_SIZE,
            24,
            int
        )

        #Load colors based on theme
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


    def apply_styling(self, text_color: str, bg_color: str, text_size: int):
        """Apply text color, background color and font size"""
        style = f"""
                <style>
                    body {{
                        color: {text_color};
                        background-color: {bg_color};
                        font-size: {text_size}pt;
                        font-family: Arial, sans-serif;
                        padding: 20px;
                        margin: 0;
                    }}
                </style>
                """

        current_content = self.transcript_display.toPlainText()

        self.transcript_display.setStyleSheet(
            f"background-color: {bg_color}; color: {text_color};"
        )

        self.translation_display.setStyleSheet(
            f"background-color: {bg_color}; color: {text_color};"
        )

        font = QFont()
        font.setPointSize(text_size)
        self.transcript_display.setFont(font)
        self.translation_display.setFont(font)

    def update_transcript(self, text: str):
        """Update the transcript display with new text"""
        # print(f"Updating transcript with text length: {len(text)}")
        self.transcript_display.setPlainText(text)
        # Force a repaint
        self.transcript_display.repaint()

    def update_translation(self, text: str):
        """Update the translation display with new text"""
        if text:
            self.translation_display.show()
            self.translation_display.setPlainText(text)
        else:
            self.translation_display.hide()


    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()





