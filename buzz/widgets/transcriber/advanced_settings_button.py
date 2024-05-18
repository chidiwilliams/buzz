from typing import Optional

from PyQt6.QtWidgets import QPushButton, QWidget

from buzz.locale import _

class AdvancedSettingsButton(QPushButton):
    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__(_("Advanced..."), parent)
