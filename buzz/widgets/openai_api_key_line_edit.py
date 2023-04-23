from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QLineEdit

from buzz.assets import get_asset_path
from buzz.icon import Icon
from buzz.widgets.line_edit import LineEdit


class OpenAIAPIKeyLineEdit(LineEdit):
    key_changed = pyqtSignal(str)

    def __init__(self, key: str, parent: QWidget):
        super().__init__(key, parent)

        self.key = key

        self.setPlaceholderText('sk-...')
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.textChanged.connect(self.on_openai_api_key_changed)
        self.toggle_show_openai_api_key_action = self.addAction(
            Icon(get_asset_path('assets/visibility_FILL0_wght700_GRAD0_opsz48.svg'), self),
            QLineEdit.ActionPosition.TrailingPosition)
        self.toggle_show_openai_api_key_action.triggered.connect(self.on_toggle_show_action_triggered)

    def on_toggle_show_action_triggered(self):
        if self.echoMode() == QLineEdit.EchoMode.Password:
            self.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.setEchoMode(QLineEdit.EchoMode.Password)

    def on_openai_api_key_changed(self, key: str):
        self.key = key
        self.key_changed.emit(key)
