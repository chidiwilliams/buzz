from typing import Optional

from PyQt6.QtWidgets import QPlainTextEdit, QWidget


class TextDisplayBox(QPlainTextEdit):
    """TextDisplayBox is a read-only textbox"""

    def __init__(self, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.setReadOnly(True)
