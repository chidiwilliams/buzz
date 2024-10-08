from typing import Optional

from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtWidgets import QDialog, QWidget, QDialogButtonBox, QMessageBox, QFormLayout

from buzz.locale import _
from buzz.widgets.line_edit import LineEdit


class ImportURLDialog(QDialog):
    url: Optional[str] = None
    url_regex = QRegularExpression(
        "^((http|https)://)[-a-zA-Z0-9@:%._\\+~#?&//=]{2,256}\\.[a-z]{2,6}\\b([-a-zA-Z0-9@:%._\\+~#?&//=]*)$"
    )

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent=parent, flags=Qt.WindowType.Window)

        self.setWindowTitle(_("Import URL"))

        self.line_edit = LineEdit()
        self.line_edit.setPlaceholderText(_("https://example.com/audio.mp3"))
        self.line_edit.setMinimumWidth(350)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText(_("Ok"))
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(_("Cancel"))
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.layout = QFormLayout()
        self.layout.addRow(_("URL:"), self.line_edit)
        self.layout.addWidget(self.button_box)
        self.setLayout(self.layout)

    def accept(self):
        if self.url_regex.match(self.line_edit.text()).hasMatch():
            self.url = self.line_edit.text()
            super().accept()
        else:
            QMessageBox.critical(
                self, _("Invalid URL"), _("The URL you entered is invalid.")
            )

    @classmethod
    def prompt(cls, parent: Optional[QWidget] = None) -> Optional[str]:
        dialog = cls(parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.url
        else:
            return None
