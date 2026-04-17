from datetime import datetime
from typing import Optional

import humanize
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QProgressDialog, QWidget, QPushButton

from buzz.locale import _
from buzz.model_loader import ModelType

NO_PROGRESS_MODEL_TYPES = {
    ModelType.HUGGING_FACE,
    ModelType.FASTER_WHISPER,
    ModelType.WHISPER_CPP,
}


class ModelDownloadProgressDialog(QProgressDialog):
    def __init__(
        self,
        model_type: ModelType,
        parent: Optional[QWidget] = None,
        modality=Qt.WindowModality.WindowModal,
    ):
        super().__init__(parent)

        self.setMinimumWidth(350)
        self.has_no_progress = model_type in NO_PROGRESS_MODEL_TYPES
        self.start_time = datetime.now()
        self.setMinimumDuration(0)
        self.setWindowModality(modality)
        self.setCancelButton(QPushButton(_("Cancel"), self))

        if self.has_no_progress:
            self.setRange(0, 0)
            self.setLabelText(_("Downloading model"))
            self.show()
        else:
            self.setRange(0, 100)
            self.update_label_text(0)

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
        if self.has_no_progress:
            return
        self.setValue(int(fraction_completed * self.maximum()))
        self.update_label_text(fraction_completed)

    def cancel(self) -> None:
        super().cancel()
