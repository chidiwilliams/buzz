import json
from typing import Optional

from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QIcon, QPixmap, QDesktopServices
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QDialogButtonBox,
    QMessageBox,
)

from buzz.__version__ import VERSION
from buzz.widgets.icon import BUZZ_ICON_PATH, BUZZ_LARGE_ICON_PATH
from buzz.locale import _
from buzz.settings.settings import APP_NAME


class AboutDialog(QDialog):
    GITHUB_API_LATEST_RELEASE_URL = (
        "https://api.github.com/repos/chidiwilliams/buzz/releases/latest"
    )
    GITHUB_LATEST_RELEASE_URL = "https://github.com/chidiwilliams/buzz/releases/latest"

    def __init__(
        self,
        network_access_manager: Optional[QNetworkAccessManager] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowIcon(QIcon(BUZZ_ICON_PATH))
        self.setWindowTitle(f'{_("About")} {APP_NAME}')

        if network_access_manager is None:
            network_access_manager = QNetworkAccessManager()

        self.network_access_manager = network_access_manager
        self.network_access_manager.finished.connect(self.on_latest_release_reply)

        layout = QVBoxLayout(self)

        image_label = QLabel()
        pixmap = QPixmap(BUZZ_LARGE_ICON_PATH).scaled(
            80,
            80,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        image_label.setPixmap(pixmap)
        image_label.setAlignment(
            Qt.AlignmentFlag(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
            )
        )

        buzz_label = QLabel(APP_NAME)
        buzz_label.setAlignment(
            Qt.AlignmentFlag(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
            )
        )
        buzz_label_font = QtGui.QFont()
        buzz_label_font.setBold(True)
        buzz_label_font.setPointSize(20)
        buzz_label.setFont(buzz_label_font)

        version_label = QLabel(f"{_('Version')} {VERSION}")
        version_label.setAlignment(
            Qt.AlignmentFlag(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
            )
        )

        self.check_updates_button = QPushButton(_("Check for updates"), self)
        self.check_updates_button.clicked.connect(self.on_click_check_for_updates)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton(QDialogButtonBox.StandardButton.Close), self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(image_label)
        layout.addWidget(buzz_label)
        layout.addWidget(version_label)
        layout.addWidget(self.check_updates_button)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def on_click_check_for_updates(self):
        url = QUrl(self.GITHUB_API_LATEST_RELEASE_URL)
        self.network_access_manager.get(QNetworkRequest(url))
        self.check_updates_button.setDisabled(True)

    def on_latest_release_reply(self, reply: QNetworkReply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            response = json.loads(reply.readAll().data())
            tag_name = response.get("name")
            if self.is_version_lower(VERSION, tag_name[1:]):
                QDesktopServices.openUrl(QUrl(self.GITHUB_LATEST_RELEASE_URL))
            else:
                QMessageBox.information(self, "", _("You're up to date!"))
        self.check_updates_button.setEnabled(True)

    @staticmethod
    def is_version_lower(version_a: str, version_b: str):
        return version_a.replace(".", "") < version_b.replace(".", "")
