import logging
from enum import Enum
from typing import Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QToolButton, QWidget, QMenu

from buzz.locale import _
from buzz.settings.shortcut import Shortcut
from buzz.settings.shortcuts import Shortcuts
from buzz.widgets.icon import VisibilityIcon


class ViewMode(Enum):
    TEXT = "Text"
    TRANSLATION = "Translation"
    TIMESTAMPS = "Timestamps"
    SPEAKERS = "Speakers"


class TranscriptionViewModeToolButton(QToolButton):
    view_mode_changed = pyqtSignal(ViewMode)

    def __init__(
            self,
            shortcuts: Shortcuts,
            has_translation: bool,
            translation: pyqtSignal,
            has_speakers: bool = False,
            parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self.setText(_("View"))
        self.setIcon(VisibilityIcon(self))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setMinimumWidth(80)

        translation.connect(self.on_translation_available)

        menu = QMenu(self)

        menu.addAction(
            _("Text"),
            QKeySequence(shortcuts.get(Shortcut.VIEW_TRANSCRIPT_TEXT)),
            lambda: self.view_mode_changed.emit(ViewMode.TEXT),
        )

        self.translation_action = menu.addAction(
            _("Translation"),
            QKeySequence(shortcuts.get(Shortcut.VIEW_TRANSCRIPT_TRANSLATION)),
            lambda: self.view_mode_changed.emit(ViewMode.TRANSLATION)
        )
        self.translation_action.setVisible(has_translation)

        menu.addAction(
            _("Timestamps"),
            QKeySequence(shortcuts.get(Shortcut.VIEW_TRANSCRIPT_TIMESTAMPS)),
            lambda: self.view_mode_changed.emit(ViewMode.TIMESTAMPS),
        )

        self.speakers_action = menu.addAction(
            _("Speakers"),
            lambda: self.view_mode_changed.emit(ViewMode.SPEAKERS),
        )
        self.speakers_action.setEnabled(has_speakers)

        self.setMenu(menu)
        self.clicked.connect(self.showMenu)

    def on_translation_available(self):
        self.translation_action.setVisible(True)

    def on_speakers_changed(self, speakers: list[str]):
        self.speakers_action.setEnabled(bool(speakers))
