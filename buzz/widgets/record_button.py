from typing import Optional

from PyQt6.QtWidgets import QPushButton, QWidget, QSizePolicy

from buzz.locale import _


class RecordButton(QPushButton):
    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__(_("Record"), parent)
        self.setDefault(True)
        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        )

    def set_stopped(self):
        self.setText(_("Record"))
        self.setDefault(True)

    def set_recording(self):
        self.setText(_("Stop"))
        self.setDefault(False)
