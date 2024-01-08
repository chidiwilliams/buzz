from typing import Optional

from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtWidgets import QDialog, QWidget, QDialogButtonBox, QVBoxLayout, QMessageBox

from buzz.locale import _
from buzz.widgets.line_edit import LineEdit


class ImportURLDialog(QDialog):
    url: Optional[str] = None

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent=parent, flags=Qt.WindowType.Window)

        self.setWindowTitle(_("Import URL"))

        self.line_edit = LineEdit()
        self.line_edit.setPlaceholderText(_("URL"))
        self.line_edit.setMinimumWidth(350)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.line_edit)
        self.layout.addWidget(self.button_box)
        self.setLayout(self.layout)

        self.setMaximumSize(0, 0)

    def accept(self):
        url_regex = QRegularExpression(
            "^((http|https)://)[-a-zA-Z0-9@:%._\\+~#?&//=]{2,256}\\.[a-z]{2,6}\\b([-a-zA-Z0-9@:%._\\+~#?&//=]*)$"
        )
        if url_regex.match(self.line_edit.text()).hasMatch():
            self.url = self.line_edit.text()
            super().accept()
        else:
            QMessageBox.critical(
                self, _("Invalid URL"), _("The URL you entered is invalid.")
            )
