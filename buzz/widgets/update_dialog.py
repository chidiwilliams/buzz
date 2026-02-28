import logging
import os
import platform
import subprocess
import tempfile
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication
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
        self._temp_file_paths: list = []
        self._pending_urls: list = []
        self._temp_dir: Optional[str] = None

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

        button_layout.addStretch()
        button_layout.addWidget(self.download_button)

        layout.addLayout(button_layout)

    def _on_download_clicked(self):
        """Starts downloading the installer"""
        if not self.update_info.download_urls:
            QMessageBox.warning(
                self,
                _("Error"),
                _("No download URL available for your platform.")
            )
            return

        self.download_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self._temp_file_paths = []
        self._pending_urls = list(self.update_info.download_urls)
        self._temp_dir = tempfile.mkdtemp()
        self._download_next_file()

    def _download_next_file(self):
        """Download the next file in the queue"""
        if not self._pending_urls:
            self._all_downloads_finished()
            return

        url_str = self._pending_urls[0]
        file_index = len(self.update_info.download_urls) - len(self._pending_urls) + 1
        total_files = len(self.update_info.download_urls)
        self.status_label.setText(
            _("Downloading file {} of {}...").format(file_index, total_files)
        )

        url = QUrl(url_str)
        request = QNetworkRequest(url)

        self._download_reply = self.network_manager.get(request)
        self._download_reply.downloadProgress.connect(self._on_download_progress)
        self._download_reply.finished.connect(self._on_download_finished)

    def _on_download_progress(self, bytes_received: int, bytes_total: int):
        """Update the progress bar during download"""
        if bytes_total > 0:
            progress = int((bytes_received / bytes_total) * 100)
            self.progress_bar.setValue(progress)

            mb_received = bytes_received / (1024 * 1024)
            mb_total = bytes_total / (1024 * 1024)
            file_index = len(self.update_info.download_urls) - len(self._pending_urls) + 1
            total_files = len(self.update_info.download_urls)
            self.status_label.setText(
                _("Downloading file {} of {} ({:.1f} MB / {:.1f} MB)...").format(
                    file_index, total_files, mb_received, mb_total
                )
            )

    def _on_download_finished(self):
        """Handles download completion for one file"""
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

        data = self._download_reply.readAll().data()
        self._download_reply.deleteLater()
        self._download_reply = None

        url_str = self._pending_urls.pop(0)

        # Extract original filename from URL to preserve it
        original_filename = QUrl(url_str).fileName()
        if not original_filename:
            original_filename = f"download_{len(self._temp_file_paths)}"

        try:
            temp_path = os.path.join(self._temp_dir, original_filename)
            with open(temp_path, "wb") as f:
                f.write(data)
            self._temp_file_paths.append(temp_path)
            logging.info(f"File saved to: {temp_path}")
        except Exception as e:
            logging.error(f"Failed to save file: {e}")
            QMessageBox.critical(
                self,
                _("Error"),
                _("Failed to save the installer: {}").format(str(e))
            )
            self._reset_ui()
            return

        self._download_next_file()

    def _all_downloads_finished(self):
        """All files downloaded, run the installer"""
        self.progress_bar.setValue(100)
        self.status_label.setText(_("Download complete!"))
        self._run_installer()

    def _run_installer(self):
        """Run the downloaded installer"""
        if not self._temp_file_paths:
            return

        installer_path = self._temp_file_paths[0]
        system = platform.system()

        try:
            if system == "Windows":
                subprocess.Popen([installer_path], shell=True)

            elif system == "Darwin":
                #open the DMG file
                subprocess.Popen(["open", installer_path])

            # Close the app so the installer can replace files
            self.accept()
            QApplication.quit()

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
        self.progress_bar.setVisible(False)
        self.status_label.setText("")

