from typing import Optional
import os

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QComboBox, QWidget
from PyQt6.QtGui import QStandardItem, QStandardItemModel

from buzz.locale import _
from buzz.transcriber.transcriber import LANGUAGES


class LanguagesComboBox(QComboBox):
    """LanguagesComboBox displays a list of languages available to use with Whisper"""

    # language is a language key from whisper.tokenizer.LANGUAGES or '' for "detect language"
    languageChanged = pyqtSignal(str)

    def __init__(
        self, default_language: Optional[str], parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)

        favorite_languages = os.getenv("BUZZ_FAVORITE_LANGUAGES", '')
        favorite_languages = favorite_languages.split(",")
        favorite_languages = [(lang, LANGUAGES[lang].title()) for lang in favorite_languages
                              if lang in LANGUAGES]
        if favorite_languages:
            favorite_languages.insert(0, ("-------", "-------"))
            favorite_languages.append(("-------", "-------"))

        whisper_languages = sorted(
            [(lang, LANGUAGES[lang].title()) for lang in LANGUAGES],
            key=lambda lang: lang[1],
        )
        self.languages = [("", _("Detect Language"))] + favorite_languages + whisper_languages

        model = QStandardItemModel()
        for lang in self.languages:
            item = QStandardItem(lang[1])
            if lang[0] == "-------":
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            model.appendRow(item)

        self.setModel(model)
        self.currentIndexChanged.connect(self.on_index_changed)

        default_language_key = default_language if default_language != "" else None
        for i, lang in enumerate(self.languages):
            if lang[0] == default_language_key:
                self.setCurrentIndex(i)

    def on_index_changed(self, index: int):
        self.languageChanged.emit(self.languages[index][0])
