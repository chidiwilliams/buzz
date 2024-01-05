from typing import Optional, List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QWidget

from buzz.model_loader import ModelType


class ModelTypeComboBox(QComboBox):
    changed = pyqtSignal(ModelType)

    def __init__(
        self,
        model_types: Optional[List[ModelType]] = None,
        default_model: Optional[ModelType] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        if model_types is None:
            model_types = [
                model_type for model_type in ModelType if model_type.is_available()
            ]

        for model_type in model_types:
            self.addItem(model_type.value)

        self.currentTextChanged.connect(self.on_text_changed)
        if default_model is not None:
            self.setCurrentText(default_model.value)

    def on_text_changed(self, text: str):
        self.changed.emit(ModelType(text))
