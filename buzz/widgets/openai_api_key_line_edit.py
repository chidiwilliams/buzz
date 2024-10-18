import logging
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QLineEdit

from buzz.assets import get_path
from buzz.widgets.icon import Icon, VisibilityIcon
from buzz.widgets.line_edit import LineEdit


class OpenAIAPIKeyLineEdit(LineEdit):
    key_changed = pyqtSignal(str)
    focus_out = pyqtSignal()

    def __init__(self, key: str, parent: Optional[QWidget] = None):
        super().__init__(key, parent)

        self.key = key

        self.visible_on_icon = VisibilityIcon(self)
        self.visible_off_icon = Icon(
            get_path("assets/visibility_off_FILL0_wght700_GRAD0_opsz48.svg"), self
        )

        self.setPlaceholderText("sk-...")
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.textChanged.connect(self.on_openai_api_key_changed)
        self.toggle_show_openai_api_key_action = self.addAction(
            self.visible_on_icon, QLineEdit.ActionPosition.TrailingPosition
        )
        self.toggle_show_openai_api_key_action.triggered.connect(
            self.on_toggle_show_action_triggered
        )

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_out.emit()

    def on_toggle_show_action_triggered(self):
        if self.echoMode() == QLineEdit.EchoMode.Password:
            self.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_show_openai_api_key_action.setIcon(self.visible_off_icon)
        else:
            self.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_show_openai_api_key_action.setIcon(self.visible_on_icon)

    def on_openai_api_key_changed(self, key: str):
        self.key = key
        self.key_changed.emit(key)
