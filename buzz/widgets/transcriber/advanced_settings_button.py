from typing import Optional

from PyQt6.QtWidgets import QPushButton, QWidget


class AdvancedSettingsButton(QPushButton):
    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__("Advanced...", parent)
