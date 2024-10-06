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
        cancel_button = QPushButton(_("Cancel"), self)
        self.setCancelButton(cancel_button)

        if not self.cancelable:
            cancel_button.setEnabled(False)

    def update_label_text(self, fraction_completed: float):
        downloading_text = _("Downloading model")
        remaining_text = _("remaining")
        label_text = f"{downloading_text} ("
        if fraction_completed > 0:
            time_spent = (datetime.now() - self.start_time).total_seconds()
            time_left = (time_spent / fraction_completed) - time_spent
            label_text += f"{humanize.naturaldelta(time_left)} {remaining_text}"
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
