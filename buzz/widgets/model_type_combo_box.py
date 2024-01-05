import sys
from typing import Optional, List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QWidget

from buzz.model_loader import ModelType
from buzz.transcriber import LOADED_WHISPER_DLL


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
            model_types = [model_type for model_type in ModelType]

        for model_type in model_types:
            if (
                # Hide Whisper.cpp option if whisper.dll did not load correctly.
                # See: https://github.com/chidiwilliams/buzz/issues/274,
                # https://github.com/chidiwilliams/buzz/issues/197
                model_type == ModelType.WHISPER_CPP and LOADED_WHISPER_DLL is False
            ) or (
                # Disable Whisper and Faster Whisper options
                # on Linux due to execstack errors on Snap
                (
                    model_type
                    in (
                        ModelType.WHISPER,
                        ModelType.FASTER_WHISPER,
                        ModelType.HUGGING_FACE,
                    )
                )
                and sys.platform == "linux"
            ):
                continue
            self.addItem(model_type.value)

        self.currentTextChanged.connect(self.on_text_changed)
        if default_model is not None:
            self.setCurrentText(default_model.value)

    def on_text_changed(self, text: str):
        self.changed.emit(ModelType(text))
