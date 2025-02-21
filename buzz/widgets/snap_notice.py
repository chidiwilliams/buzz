from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel, QPushButton
from buzz.locale import _


class SnapNotice(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(_("Snap permission notice"))

        self.layout = QVBoxLayout(self)

        self.notice_label = QLabel(_("Detected missing permissions, please check that snap permissions have been granted"))
        self.layout.addWidget(self.notice_label)

        self.instruction_label = QLabel(_("To enable necessary permissions run the following commands in the terminal"))
        self.layout.addWidget(self.instruction_label)

        self.text_edit = QTextEdit(self)
        self.text_edit.setPlainText(
            "sudo snap connect buzz:password-manager-service\n"
        )
        self.text_edit.setReadOnly(True)
        self.text_edit.setFixedHeight(80)
        self.layout.addWidget(self.text_edit)

        self.button = QPushButton(_("Close"), self)
        self.button.clicked.connect(self.close)
        self.layout.addWidget(self.button)