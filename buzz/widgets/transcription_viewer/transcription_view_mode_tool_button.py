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


class TranscriptionViewModeToolButton(QToolButton):
    view_mode_changed = pyqtSignal(ViewMode)

    def __init__(
            self,
            shortcuts: Shortcuts,
            has_translation: bool,
            translation: pyqtSignal,
            parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self.setText(_("View"))
        self.setIcon(VisibilityIcon(self))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

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

        self.setMenu(menu)

    def on_translation_available(self):
        self.translation_action.setVisible(True)
