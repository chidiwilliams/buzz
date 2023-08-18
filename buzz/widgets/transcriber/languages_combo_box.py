from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QWidget

from buzz.locale import _
from buzz.transcriber import LANGUAGES


class LanguagesComboBox(QComboBox):
    """LanguagesComboBox displays a list of languages available to use with Whisper"""

    # language is a language key from whisper.tokenizer.LANGUAGES or '' for "detect language"
    languageChanged = pyqtSignal(str)

    def __init__(
        self, default_language: Optional[str], parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)

        whisper_languages = sorted(
            [(lang, LANGUAGES[lang].title()) for lang in LANGUAGES],
            key=lambda lang: lang[1],
        )
        self.languages = [("", _("Detect Language"))] + whisper_languages

        self.addItems([lang[1] for lang in self.languages])
        self.currentIndexChanged.connect(self.on_index_changed)

        default_language_key = default_language if default_language != "" else None
        for i, lang in enumerate(self.languages):
            if lang[0] == default_language_key:
                self.setCurrentIndex(i)

    def on_index_changed(self, index: int):
        self.languageChanged.emit(self.languages[index][0])
