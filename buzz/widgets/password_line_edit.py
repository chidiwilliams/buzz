from typing import Optional

from PyQt6.QtWidgets import QWidget, QLineEdit

from buzz.assets import get_path
from buzz.widgets.icon import Icon, VisibilityIcon
from buzz.widgets.line_edit import LineEdit


class PasswordLineEdit(LineEdit):
    """A masked text input with a trailing show/hide toggle."""

    def __init__(
        self,
        text: str = "",
        placeholder: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)

        self.visible_on_icon = VisibilityIcon(self)
        self.visible_off_icon = Icon(
            get_path("assets/visibility_off_FILL0_wght700_GRAD0_opsz48.svg"), self
        )

        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.toggle_show_action = self.addAction(
            self.visible_on_icon, QLineEdit.ActionPosition.TrailingPosition
        )
        self.toggle_show_action.triggered.connect(self.on_toggle_show_action_triggered)

    def on_toggle_show_action_triggered(self):
        if self.echoMode() == QLineEdit.EchoMode.Password:
            self.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_show_action.setIcon(self.visible_off_icon)
        else:
            self.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_show_action.setIcon(self.visible_on_icon)
