from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget


class FormLabel(QLabel):
    def __init__(self, name: str, parent: Optional[QWidget], *args) -> None:
        super().__init__(name, parent, *args)
        self.setStyleSheet("QLabel { text-align: right; }")
        self.setAlignment(
            Qt.AlignmentFlag(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            )
        )
