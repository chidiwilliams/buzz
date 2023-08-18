import platform
from typing import Optional

from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QKeySequenceEdit, QWidget


class SequenceEdit(QKeySequenceEdit):
    def __init__(self, sequence: str, parent: Optional[QWidget] = None):
        super().__init__(sequence, parent)
        self.setClearButtonEnabled(True)
        if platform.system() == "Darwin":
            self.setStyleSheet("QLineEdit:focus { border: 2px solid #4d90fe; }")

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        # The shortcut editor always focuses on the sequence edit widgets, so we need to
        # manually capture Esc key presses to close the dialog. The downside being that
        # the user can't set a shortcut that contains the Esc key.
        if key == Qt.Key.Key_Escape:
            self.parent().keyPressEvent(event)
            return

        # Ignore pressing *only* modifier keys
        if (
            key == Qt.Key.Key_Control
            or key == Qt.Key.Key_Shift
            or key == Qt.Key.Key_Alt
            or key == Qt.Key.Key_Meta
        ):
            return

        super().keyPressEvent(event)
