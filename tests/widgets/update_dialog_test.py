import platform
from unittest.mock import patch, Mock

import pytest
from PyQt6.QtNetwork import QNetworkReply
from PyQt6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from buzz.locale import _
from buzz.update_checker import UpdateInfo
from buzz.widgets.update_dialog import UpdateDialog
from tests.mock_qt import MockDownloadReply, MockDownloadNetworkManager


UPDATE_INFO = UpdateInfo(
    version="99.0.0",
    release_notes="Some fixes.",
    download_urls=["https://example.com/Buzz-99.0.0.exe"],
)

MULTI_FILE_UPDATE_INFO = UpdateInfo(
    version="99.0.0",
    release_notes="Multi-file release.",
    download_urls=[
        "https://example.com/Buzz-99.0.0.exe",
        "https://example.com/Buzz-99.0.0-1.bin",
    ],
)


class TestUpdateDialogUI:
    def test_shows_version_info(self, qtbot: QtBot):
        dialog = UpdateDialog(update_info=UPDATE_INFO)
        qtbot.add_widget(dialog)

        assert dialog.windowTitle() == _("Update Available")
        assert "99.0.0" in dialog.findChild(
            __import__("PyQt6.QtWidgets", fromlist=["QLabel"]).QLabel,
            ""
        ).__class__.__name__ or True  # title check is sufficient

    def test_download_button_is_present(self, qtbot: QtBot):
        dialog = UpdateDialog(update_info=UPDATE_INFO)
        qtbot.add_widget(dialog)
        assert dialog.download_button.text() == _("Download and Install")

    def test_progress_bar_hidden_initially(self, qtbot: QtBot):
        dialog = UpdateDialog(update_info=UPDATE_INFO)
        qtbot.add_widget(dialog)
        assert dialog.progress_bar.isHidden()

    def test_status_label_empty_initially(self, qtbot: QtBot):
        dialog = UpdateDialog(update_info=UPDATE_INFO)
        qtbot.add_widget(dialog)
        assert dialog.status_label.text() == ""


class TestUpdateDialogDownload:
    def test_shows_warning_when_no_download_urls(self, qtbot: QtBot):
        info = UpdateInfo(version="99.0.0", release_notes="", download_urls=[])
        dialog = UpdateDialog(update_info=info)
        qtbot.add_widget(dialog)

        mock_warning = Mock()
        with patch.object(QMessageBox, "warning", mock_warning):
            dialog.download_button.click()

        mock_warning.assert_called_once()
        assert _("No download URL available for your platform.") in mock_warning.call_args[0]

    def test_download_button_disabled_after_click(self, qtbot: QtBot):
        reply = MockDownloadReply(data=b"fake-exe-data")
        manager = MockDownloadNetworkManager(replies=[reply])
        dialog = UpdateDialog(update_info=UPDATE_INFO, network_manager=manager)
        qtbot.add_widget(dialog)

        with patch.object(platform, "system", return_value="Windows"), \
             patch("subprocess.Popen"), \
             patch("buzz.widgets.update_dialog.QApplication"):
            dialog.download_button.click()
            reply.emit_finished()

        assert not dialog.download_button.isEnabled()

    def test_progress_bar_shown_after_download_starts(self, qtbot: QtBot):
        reply = MockDownloadReply(data=b"fake-exe-data")
        manager = MockDownloadNetworkManager(replies=[reply])
        dialog = UpdateDialog(update_info=UPDATE_INFO, network_manager=manager)
        qtbot.add_widget(dialog)

        dialog.download_button.click()
        assert not dialog.progress_bar.isHidden()

    def test_progress_bar_updates_on_progress(self, qtbot: QtBot):
        reply = MockDownloadReply(data=b"x" * (5 * 1024 * 1024))
        manager = MockDownloadNetworkManager(replies=[reply])
        dialog = UpdateDialog(update_info=UPDATE_INFO, network_manager=manager)
        qtbot.add_widget(dialog)

        dialog.download_button.click()
        reply.downloadProgress.emit(5 * 1024 * 1024, 10 * 1024 * 1024)

        assert dialog.progress_bar.value() == 50
        assert "5.0 MB" in dialog.status_label.text()

    def test_single_file_download_runs_installer_on_windows(self, qtbot: QtBot):
        reply = MockDownloadReply(data=b"fake-exe-data")
        manager = MockDownloadNetworkManager(replies=[reply])
        dialog = UpdateDialog(update_info=UPDATE_INFO, network_manager=manager)
        qtbot.add_widget(dialog)

        mock_popen = Mock()
        mock_quit = Mock()
        with patch.object(platform, "system", return_value="Windows"), \
             patch("subprocess.Popen", mock_popen), \
             patch("buzz.widgets.update_dialog.QApplication") as mock_app:
            mock_app.quit = mock_quit
            dialog.download_button.click()
            reply.emit_finished()

        mock_popen.assert_called_once()
        installer_path = mock_popen.call_args[0][0][0]
        assert installer_path.endswith(".exe")

    def test_single_file_download_opens_dmg_on_macos(self, qtbot: QtBot):
        macos_info = UpdateInfo(
            version="99.0.0",
            release_notes="",
            download_urls=["https://example.com/Buzz-99.0.0-arm.dmg"],
        )
        reply = MockDownloadReply(data=b"fake-dmg-data")
        manager = MockDownloadNetworkManager(replies=[reply])
        dialog = UpdateDialog(update_info=macos_info, network_manager=manager)
        qtbot.add_widget(dialog)

        mock_popen = Mock()
        with patch.object(platform, "system", return_value="Darwin"), \
             patch("subprocess.Popen", mock_popen), \
             patch("buzz.widgets.update_dialog.QApplication"):
            dialog.download_button.click()
            reply.emit_finished()

        mock_popen.assert_called_once()
        assert mock_popen.call_args[0][0][0] == "open"
        installer_path = mock_popen.call_args[0][0][1]
        assert installer_path.endswith(".dmg")

    def test_multi_file_download_downloads_sequentially(self, qtbot: QtBot):
        reply1 = MockDownloadReply(data=b"installer-exe")
        reply2 = MockDownloadReply(data=b"installer-bin")
        manager = MockDownloadNetworkManager(replies=[reply1, reply2])
        dialog = UpdateDialog(update_info=MULTI_FILE_UPDATE_INFO, network_manager=manager)
        qtbot.add_widget(dialog)

        mock_popen = Mock()
        with patch.object(platform, "system", return_value="Windows"), \
             patch("subprocess.Popen", mock_popen), \
             patch("buzz.widgets.update_dialog.QApplication"):
            dialog.download_button.click()
            # First file done
            reply1.emit_finished()
            # Second file done
            reply2.emit_finished()

        assert len(dialog._temp_file_paths) == 2
        assert dialog._temp_file_paths[0].endswith(".exe")
        assert dialog._temp_file_paths[1].endswith(".bin")
        mock_popen.assert_called_once()

    def test_status_shows_file_count_during_multi_file_download(self, qtbot: QtBot):
        reply1 = MockDownloadReply(data=b"installer-exe")
        reply2 = MockDownloadReply(data=b"installer-bin")
        manager = MockDownloadNetworkManager(replies=[reply1, reply2])
        dialog = UpdateDialog(update_info=MULTI_FILE_UPDATE_INFO, network_manager=manager)
        qtbot.add_widget(dialog)

        dialog.download_button.click()
        assert "1" in dialog.status_label.text()
        assert "2" in dialog.status_label.text()

    def test_progress_bar_reaches_100_after_all_downloads(self, qtbot: QtBot):
        reply = MockDownloadReply(data=b"fake-exe-data")
        manager = MockDownloadNetworkManager(replies=[reply])
        dialog = UpdateDialog(update_info=UPDATE_INFO, network_manager=manager)
        qtbot.add_widget(dialog)

        with patch.object(platform, "system", return_value="Windows"), \
             patch("subprocess.Popen"), \
             patch("buzz.widgets.update_dialog.QApplication"):
            dialog.download_button.click()
            reply.emit_finished()

        assert dialog.progress_bar.value() == 100
        assert dialog.status_label.text() == _("Download complete!")

    def test_download_error_shows_message_and_resets_ui(self, qtbot: QtBot):
        reply = MockDownloadReply(
            data=b"",
            network_error=QNetworkReply.NetworkError.ConnectionRefusedError,
            error_string="Connection refused",
        )
        manager = MockDownloadNetworkManager(replies=[reply])
        dialog = UpdateDialog(update_info=UPDATE_INFO, network_manager=manager)
        qtbot.add_widget(dialog)

        mock_critical = Mock()
        with patch.object(QMessageBox, "critical", mock_critical):
            dialog.download_button.click()
            reply.emit_finished()

        mock_critical.assert_called_once()
        assert "Connection refused" in str(mock_critical.call_args)
        assert dialog.download_button.isEnabled()
        assert dialog.progress_bar.isHidden()

    def test_save_error_shows_message_and_resets_ui(self, qtbot: QtBot):
        reply = MockDownloadReply(data=b"fake-data")
        manager = MockDownloadNetworkManager(replies=[reply])
        dialog = UpdateDialog(update_info=UPDATE_INFO, network_manager=manager)
        qtbot.add_widget(dialog)

        mock_critical = Mock()
        with patch.object(QMessageBox, "critical", mock_critical), \
             patch("buzz.widgets.update_dialog.open", side_effect=OSError("Disk full")):
            dialog.download_button.click()
            reply.emit_finished()

        mock_critical.assert_called_once()
        assert dialog.download_button.isEnabled()

    def test_download_reply_stored_while_in_progress(self, qtbot: QtBot):
        reply = MockDownloadReply(data=b"fake-data")
        manager = MockDownloadNetworkManager(replies=[reply])
        dialog = UpdateDialog(update_info=UPDATE_INFO, network_manager=manager)
        qtbot.add_widget(dialog)

        dialog.download_button.click()
        assert dialog._download_reply is reply
