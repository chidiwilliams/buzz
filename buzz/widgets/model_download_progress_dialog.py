from datetime import datetime
from typing import Optional

import humanize
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QProgressDialog, QWidget, QPushButton

from buzz.locale import _
from buzz.model_loader import ModelType


class ModelDownloadProgressDialog(QProgressDialog):
    def __init__(
        self,
        model_type: ModelType,
        parent: Optional[QWidget] = None,
        modality=Qt.WindowModality.WindowModal,
    ):
        super().__init__(parent)

        self.cancelable = (
            model_type == ModelType.WHISPER or model_type == ModelType.WHISPER_CPP
        )
        self.start_time = datetime.now()
        self.setRange(0, 100)
        self.setMinimumDuration(0)
        self.setWindowModality(modality)
        self.update_label_text(0)

        if not self.cancelable:
            cancel_button = QPushButton("Cancel", self)
            cancel_button.setEnabled(False)
            self.setCancelButton(cancel_button)

    def update_label_text(self, fraction_completed: float):
        label_text = f"{_('Downloading model')} ({fraction_completed:.0%}"
        if fraction_completed > 0:
            time_spent = (datetime.now() - self.start_time).total_seconds()
            time_left = (time_spent / fraction_completed) - time_spent
            label_text += f", {humanize.naturaldelta(time_left)} {_('remaining')}"
        label_text += ")"

        self.setLabelText(label_text)

    def set_value(self, fraction_completed: float):
        if self.wasCanceled():
            return
        self.setValue(int(fraction_completed * self.maximum()))
        self.update_label_text(fraction_completed)

    def cancel(self) -> None:
        if self.cancelable:
            super().cancel()
