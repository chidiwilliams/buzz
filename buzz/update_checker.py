import json
import logging
import platform
from datetime import datetime, timedelta
from typing import Optional, Callable
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal, QUrl
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from buzz.__version__ import VERSION
from buzz.settings.settings import Settings


@dataclass
class UpdateInfo:
    version: str
    release_notes: str
    download_url: str

class UpdateChecker(QObject):
    update_available = pyqtSignal(object)

    no_update_available = pyqtSignal()

    check_failed = pyqtSignal(str)

    VERSION_JSON_URL = "https://raw.githubusercontent.com/chidiwilliams/buzz/refs/heads/main/version.json"

    CHECK_INTERVAL_DAYS = 7

    def __init__(
        self,
        settings: Settings,
        network_manager: Optional[QNetworkAccessManager] = None,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)

        self.settings = settings

        if network_manager is None:
            network_manager = QNetworkAccessManager(self)
        self.network_manager = network_manager
        self.network_manager.finished.connect(self._on_reply_finished)

        self._force_check = False


    def should_check_for_updates(self) -> bool:
        """"Check if we are on Windows/macOS and if 7 days passed"""
        system = platform.system()
        if system not in ("Windows", "Darwin"):
            logging.debug("Skipping update check on linux")
            return False

        last_check = self.settings.value(
            Settings.Key.LAST_UPDATE_CHECK,
            "",
        )

        if last_check:
            try:
                last_check_date = datetime.fromisoformat(last_check)
                days_since_check = (datetime.now() - last_check_date).days
                if days_since_check < self.CHECK_INTERVAL_DAYS:
                    logging.debug(
                        f"Skipping update check, last checked {days_since_check} days ago"
                    )
                    return False
            except ValueError:
                #Invalid date format
                pass

        return True

    def check_for_updates(self, force: bool = False) -> None:
        """Start the network request"""
        self._force_check = force

        if not force and not self.should_check_for_updates():
            self.no_update_available.emit()
            return

        logging.info("Checking for updates...")

        url = QUrl(self.VERSION_JSON_URL)
        request = QNetworkRequest(url)
        self.network_manager.get(request)

    def _on_reply_finished(self, reply: QNetworkReply) -> None:
        """Handles the network reply for version.json fetch"""
        self.settings.set_value(
            Settings.Key.LAST_UPDATE_CHECK,
            datetime.now().isoformat()
        )

        if reply.error() != QNetworkReply.NetworkError.NoError:
            error_msg = f"Failed to check for updates: {reply.errorString()}"
            logging.error(error_msg)
            self.check_failed.emit(error_msg)
            reply.deleteLater()
            return

        try:
            data = json.loads(reply.readAll().data().decode("utf-8"))
            reply.deleteLater()

            remote_version = data.get("version", "")
            release_notes = data.get("release_notes", "")
            download_urls = data.get("download_urls", {})

            #Get the download url for current platform
            download_url = self._get_download_url(download_urls)

            if self._is_newer_version(remote_version):
                logging.info(f"Update available: {remote_version}")

                #Store the available version
                self.settings.set_value(
                    Settings.Key.UPDATE_AVAILABLE_VERSION,
                    remote_version
                )

                update_info = UpdateInfo(
                    version=remote_version,
                    release_notes=release_notes,
                    download_url=download_url
                )
                self.update_available.emit(update_info)

            else:
                logging.info("No update available")
                self.settings.set_value(
                    Settings.Key.UPDATE_AVAILABLE_VERSION,
                    ""
                )
                self.no_update_available.emit()

        except (json.JSONDecodeError, KeyError) as e:
            error_msg = f"Failed to parse version info: {e}"
            logging.error(error_msg)
            self.check_failed.emit(error_msg)

    def _get_download_url(self, download_urls: dict) -> str:
        system = platform.system()
        machine = platform.machine().lower()

        if system == "Windows":
            return download_urls.get("windows_x64", "")
        elif system == "Darwin":
            if machine in ("arm64", "aarch64"):
                return download_urls.get("macos_arm", "")
            else:
                return download_urls.get("macos_x86", "")

        return ""

    def _is_newer_version(self, remote_version: str) -> bool:
        """Compare remote version with current version"""
        try:
            current_parts = [int(x) for x in VERSION.split(".")]
            remote_parts = [int(x) for x in remote_version.split(".")]

            #pad with zeros if needed
            while len(current_parts) < len(remote_parts):
                current_parts.append(0)
            while len(remote_parts) < len(current_parts):
                remote_parts.append(0)

            return remote_parts > current_parts

        except ValueError:
            logging.error(f"Invalid version format: {VERSION} or {remote_version}")
            return False




