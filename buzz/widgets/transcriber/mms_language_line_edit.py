from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QSizePolicy

from buzz.locale import _
from buzz.widgets.line_edit import LineEdit


class MMSLanguageLineEdit(LineEdit):
    """Text input for MMS language codes (ISO 639-3).

    MMS models support 1000+ languages using ISO 639-3 codes (3 letters).
    Examples: eng (English), fra (French), deu (German), spa (Spanish)
    """

    languageChanged = pyqtSignal(str)

    def __init__(
        self,
        default_language: str = "eng",
        parent: Optional[QWidget] = None
    ):
        super().__init__(default_language, parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setPlaceholderText(_("e.g., eng, fra, deu"))
        self.setToolTip(
            _("Enter an ISO 639-3 language code (3 letters).\n"
              "Examples: eng (English), fra (French), deu (German),\n"
              "spa (Spanish), lav (Latvian)")
        )
        self.setMaxLength(10)  # Allow some flexibility for edge cases
        self.setMinimumWidth(100)

        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str):
        """Emit language changed signal with cleaned text."""
        cleaned = text.strip().lower()
        self.languageChanged.emit(cleaned)

    def language(self) -> str:
        """Get the current language code."""
        return self.text().strip().lower()

    def setLanguage(self, language: str):
        """Set the language code."""
        self.setText(language.strip().lower() if language else "eng")
