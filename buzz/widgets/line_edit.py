import platform
from typing import Optional

from PyQt6.QtWidgets import QLineEdit, QWidget


class LineEdit(QLineEdit):
    def __init__(self, default_text: str = "", parent: Optional[QWidget] = None):
        super().__init__(default_text, parent)
        if platform.system() == "Darwin":
            self.setStyleSheet("QLineEdit { padding: 4px }")
