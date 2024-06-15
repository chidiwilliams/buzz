from PyQt6.QtWidgets import QPlainTextEdit, QWidget

from buzz.locale import _
from buzz.model_loader import ModelType


class InitialPromptTextEdit(QPlainTextEdit):
    def __init__(self, text: str, model_type: ModelType, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setPlaceholderText(_("Enter prompt..."))
        self.setEnabled(model_type.supports_initial_prompt)
        self.setMinimumWidth(350)
        self.setFixedHeight(115)
