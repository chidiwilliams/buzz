from typing import Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QToolButton, QWidget, QMenu

from buzz.locale import _
from buzz.settings.shortcut import Shortcut
from buzz.settings.shortcuts import Shortcuts
from buzz.widgets.icon import VisibilityIcon


class TranscriptionViewModeToolButton(QToolButton):
    view_mode_changed = pyqtSignal(bool)  # is_timestamps?

    def __init__(self, shortcuts: Shortcuts, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setText(_("View"))
        self.setIcon(VisibilityIcon(self))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        menu = QMenu(self)

        menu.addAction(
            _("Text"),
            QKeySequence(shortcuts.get(Shortcut.VIEW_TRANSCRIPT_TEXT)),
            lambda: self.view_mode_changed.emit(False),
        )

        menu.addAction(
            _("Timestamps"),
            QKeySequence(shortcuts.get(Shortcut.VIEW_TRANSCRIPT_TIMESTAMPS)),
            lambda: self.view_mode_changed.emit(True),
        )
        self.setMenu(menu)
