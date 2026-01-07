import logging
import os
import platform
import subprocess
import tempfile
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QMessageBox,
    QWidget,
    QTextEdit,
)

from buzz.__version__ import VERSION
from buzz.locale import _
from buzz.update_checker import UpdateInfo
from buzz.widgets.icon import BUZZ_ICON_PATH

class UpdateDialog(QDialog):
    """Dialog shows when an update is available"""
    def __init__(
        self,
        update_info: UpdateInfo,
        network_manager: Optional[QNetworkAccessManager] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self.update_info = update_info

        if network_manager is None:
            network_manager = QNetworkAccessManager(self)
        self.network_manager = network_manager

        self._download_reply: Optional[QNetworkReply] = None
        self._temp_file_path: Optional[str] = None

        self._setup_ui()


    def _setup_ui(self):
        self.setWindowTitle(_("Update Available"))
        self.setWindowIcon(QIcon(BUZZ_ICON_PATH))
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        #header
        header_label = QLabel(
            _("A new version of Buzz is available!")
        )

        header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header_label)

        #Version info
        version_layout = QHBoxLayout()

        current_version_label = QLabel(_("Current version:"))
        current_version_value = QLabel(f"<b>{VERSION}</b>")

        new_version_label = QLabel(_("New version:"))
        new_version_value = QLabel(f"<b>{self.update_info.version}</b>")
        new_version_value.setStyleSheet("color: green;")

        version_layout.addWidget(current_version_label)
        version_layout.addWidget(current_version_value)
        version_layout.addStretch()
        version_layout.addWidget(new_version_label)
        version_layout.addWidget(new_version_value)

        layout.addLayout(version_layout)

        #Release notes
        if self.update_info.release_notes:
            notes_label = QLabel(_("Release Notes:"))
            notes_label.setStyleSheet("font-weight: bold;")
            layout.addWidget(notes_label)

            notes_text = QTextEdit()
            notes_text.setReadOnly(True)
            notes_text.setMarkdown(self.update_info.release_notes)
            notes_text.setMaximumHeight(150)
            layout.addWidget(notes_text)

        #progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        #Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        #Buttons
        button_layout = QVBoxLayout()

        self.download_button = QPushButton(_("Download and Install"))
        self.download_button.clicked.connect(self._on_download_clicked)
        self.download_button.setDefault(True)

        self.cancel_button = QPushButton(_("Later"))
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.download_button)

        layout.addLayout(button_layout)

    def _on_download_clicked(self):
        """Starts downloading the installer"""
        if not self.update_info.download_url:
            QMessageBox.warning(
                self,
                _("Error"),
                _("No download URL available for your platform.")
            )
            return

        self.download_button.setEnabled(False)
        self.cancel_button.setText(_("Cancel"))
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(_("Downloading..."))

        url = QUrl(self.update_info.download_url)
        request = QNetworkRequest(url)

        self._download_reply = self.network_manager.get(request)
        self._download_reply.downloadProgress.connect(self._on_download_progress)
        self._download_reply.finished.connect(self._on_download_finished)

    def _on_download_progress(self, bytes_received: int, bytes_total: int):
        """Update the progress bar during download"""
        if bytes_total > 0:
            progress = int((bytes_received / bytes_total) * 100)
            self.progress_bar.setValue(progress)

            #show size info
            mb_received = bytes_received / (1024 * 1024)
            mb_total = bytes_total / (1024 * 1024)
            self.status_label.setText(
                _("Downloading... {:.1f} MB / {:.1f} MB").format(mb_received, mb_total)
            )

    def _on_download_finished(self):
        """Handles download completion"""
        if self._download_reply is None:
            return

        if self._download_reply.error() != QNetworkReply.NetworkError.NoError:
            error_msg = self._download_reply.errorString()
            logging.error(f"Download failed: {error_msg}")

            QMessageBox.critical(
                self,
                _("Download Failed"),
                _("Failed to download the update: {}").format(error_msg)
            )

            self._reset_ui()
            self._download_reply.deleteLater()
            self._download_reply = None
            return

        #save to temp file
        data = self._download_reply.readAll().data()
        self._download_reply.deleteLater()
        self._download_reply = None

        #determine file extension based on patform
        system = platform.system()
        if system == "Windows":
            suffix = ".exe"
        elif system == "Darwin":
            suffix = ".dmg"
        else:
            suffix = ""

        try:
            #temp file
            fd, self._temp_file_path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as f:
                f.write(data)

            logging.info(f"Installer saved to: {self._temp_file_path}")

            self.progress_bar.setValue(100)
            self.status_label.setText(_("Download complete!"))

            #run the installer
            self._run_installer()

        except Exception as e:
            logging.error(f"Failed to save installer: {e}")
            QMessageBox.critical(
                self,
                _("Error"),
                _("Failed to save the installer: {}").format(str(e))
            )
            self._reset_ui()


    def _run_installer(self):
        """Run the downloaded installer"""
        if not self._temp_file_path:
            return

        system = platform.system()

        try:
            if system == "Windows":
                self.status_label.setText(_("Launching installer..."))
                subprocess.Popen([self._temp_file_path], shell=True)
                self.accept()

            elif system == "Darwin":
                #open the DMG file
                self.status_label.setText(_("Opening disk image..."))
                subprocess.Popen(["open", self._temp_file_path])

                QMessageBox.information(
                    self,
                    _("Install Update"),
                    _("The disk image has been opened. Please drag Buzz to your Applications folder to complete the update.")
                )
                self.accept()

        except Exception as e:
            logging.error(f"Failed to run installer: {e}")
            QMessageBox.critical(
                self,
                _("Error"),
                _("Failed to run the installer: {}").format(str(e))
            )


    def _reset_ui(self):
        """Reset the UI to initial state after an error"""
        self.download_button.setEnabled(True)
        self.cancel_button.setText(_("Later"))
        self.progress_bar.setVisible(False)
        self.status_label.setText("")


    def reject(self):
        """Cancel download in progress when user clicks Cancel or Later"""
        if self._download_reply is not None:
            self._download_reply.abort()
            self._download_reply.deleteLater()
            self._download_reply = None

        super().reject()







