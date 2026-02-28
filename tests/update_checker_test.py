import platform
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from pytestqt.qtbot import QtBot

from buzz.__version__ import VERSION
from buzz.settings.settings import Settings
from buzz.update_checker import UpdateChecker, UpdateInfo
from tests.mock_qt import MockNetworkAccessManager, MockNetworkReply


VERSION_INFO = {
    "version": "99.0.0",
    "release_notes": "Some fixes.",
    "download_urls": {
        "windows_x64": ["https://example.com/Buzz-99.0.0.exe"],
        "macos_arm": ["https://example.com/Buzz-99.0.0-arm.dmg"],
        "macos_x86": ["https://example.com/Buzz-99.0.0-x86.dmg"],
    },
}


@pytest.fixture()
def checker(settings: Settings) -> UpdateChecker:
    reply = MockNetworkReply(data=VERSION_INFO)
    manager = MockNetworkAccessManager(reply=reply)
    return UpdateChecker(settings=settings, network_manager=manager)


class TestShouldCheckForUpdates:
    def test_returns_false_on_linux(self, checker: UpdateChecker):
        with patch.object(platform, "system", return_value="Linux"):
            assert checker.should_check_for_updates() is False

    def test_returns_true_on_windows_first_run(self, checker: UpdateChecker, settings: Settings):
        settings.set_value(Settings.Key.LAST_UPDATE_CHECK, "")
        with patch.object(platform, "system", return_value="Windows"):
            assert checker.should_check_for_updates() is True

    def test_returns_true_on_macos_first_run(self, checker: UpdateChecker, settings: Settings):
        settings.set_value(Settings.Key.LAST_UPDATE_CHECK, "")
        with patch.object(platform, "system", return_value="Darwin"):
            assert checker.should_check_for_updates() is True

    def test_returns_false_when_checked_recently(
        self, checker: UpdateChecker, settings: Settings
    ):
        recent = (datetime.now() - timedelta(days=2)).isoformat()
        settings.set_value(Settings.Key.LAST_UPDATE_CHECK, recent)

        with patch.object(platform, "system", return_value="Windows"):
            assert checker.should_check_for_updates() is False

    def test_returns_true_when_check_is_overdue(
        self, checker: UpdateChecker, settings: Settings
    ):
        old = (datetime.now() - timedelta(days=10)).isoformat()
        settings.set_value(Settings.Key.LAST_UPDATE_CHECK, old)

        with patch.object(platform, "system", return_value="Windows"):
            assert checker.should_check_for_updates() is True

    def test_returns_true_on_invalid_date_in_settings(
        self, checker: UpdateChecker, settings: Settings
    ):
        settings.set_value(Settings.Key.LAST_UPDATE_CHECK, "not-a-date")

        with patch.object(platform, "system", return_value="Windows"):
            assert checker.should_check_for_updates() is True


class TestIsNewerVersion:
    def test_newer_major(self, checker: UpdateChecker):
        with patch("buzz.update_checker.VERSION", "1.0.0"):
            assert checker._is_newer_version("2.0.0") is True

    def test_newer_minor(self, checker: UpdateChecker):
        with patch("buzz.update_checker.VERSION", "1.0.0"):
            assert checker._is_newer_version("1.1.0") is True

    def test_newer_patch(self, checker: UpdateChecker):
        with patch("buzz.update_checker.VERSION", "1.0.0"):
            assert checker._is_newer_version("1.0.1") is True

    def test_same_version(self, checker: UpdateChecker):
        with patch("buzz.update_checker.VERSION", "1.0.0"):
            assert checker._is_newer_version("1.0.0") is False

    def test_older_version(self, checker: UpdateChecker):
        with patch("buzz.update_checker.VERSION", "2.0.0"):
            assert checker._is_newer_version("1.9.9") is False

    def test_different_segment_count(self, checker: UpdateChecker):
        with patch("buzz.update_checker.VERSION", "1.0"):
            assert checker._is_newer_version("1.0.1") is True

    def test_invalid_version_returns_false(self, checker: UpdateChecker):
        with patch("buzz.update_checker.VERSION", "1.0.0"):
            assert checker._is_newer_version("not-a-version") is False


class TestGetDownloadUrl:
    def test_windows_returns_windows_urls(self, checker: UpdateChecker):
        with patch.object(platform, "system", return_value="Windows"):
            urls = checker._get_download_url(VERSION_INFO["download_urls"])
            assert urls == ["https://example.com/Buzz-99.0.0.exe"]

    def test_macos_arm_returns_arm_urls(self, checker: UpdateChecker):
        with patch.object(platform, "system", return_value="Darwin"), \
             patch.object(platform, "machine", return_value="arm64"):
            urls = checker._get_download_url(VERSION_INFO["download_urls"])
            assert urls == ["https://example.com/Buzz-99.0.0-arm.dmg"]

    def test_macos_x86_returns_x86_urls(self, checker: UpdateChecker):
        with patch.object(platform, "system", return_value="Darwin"), \
             patch.object(platform, "machine", return_value="x86_64"):
            urls = checker._get_download_url(VERSION_INFO["download_urls"])
            assert urls == ["https://example.com/Buzz-99.0.0-x86.dmg"]

    def test_linux_returns_empty(self, checker: UpdateChecker):
        with patch.object(platform, "system", return_value="Linux"):
            urls = checker._get_download_url(VERSION_INFO["download_urls"])
            assert urls == []

    def test_wraps_plain_string_in_list(self, checker: UpdateChecker):
        with patch.object(platform, "system", return_value="Windows"):
            urls = checker._get_download_url({"windows_x64": "https://example.com/a.exe"})
            assert urls == ["https://example.com/a.exe"]


class TestCheckForUpdates:
    def _make_checker(self, settings: Settings, version_data: dict) -> UpdateChecker:
        settings.set_value(Settings.Key.LAST_UPDATE_CHECK, "")
        reply = MockNetworkReply(data=version_data)
        manager = MockNetworkAccessManager(reply=reply)
        return UpdateChecker(settings=settings, network_manager=manager)

    def test_emits_update_available_when_newer_version(self, settings: Settings):
        received = []
        checker = self._make_checker(settings, VERSION_INFO)
        checker.update_available.connect(lambda info: received.append(info))

        with patch.object(platform, "system", return_value="Windows"), \
             patch.object(platform, "machine", return_value="x86_64"), \
             patch("buzz.update_checker.VERSION", "1.0.0"):
            checker.check_for_updates()

        assert len(received) == 1
        update_info: UpdateInfo = received[0]
        assert update_info.version == "99.0.0"
        assert update_info.release_notes == "Some fixes."
        assert update_info.download_urls == ["https://example.com/Buzz-99.0.0.exe"]

    def test_does_not_emit_when_version_is_current(self, settings: Settings):
        received = []
        checker = self._make_checker(settings, {**VERSION_INFO, "version": VERSION})
        checker.update_available.connect(lambda info: received.append(info))

        with patch.object(platform, "system", return_value="Windows"):
            checker.check_for_updates()

        assert received == []

    def test_skips_network_call_on_linux(self, settings: Settings):
        received = []
        checker = self._make_checker(settings, VERSION_INFO)
        checker.update_available.connect(lambda info: received.append(info))

        with patch.object(platform, "system", return_value="Linux"):
            checker.check_for_updates()

        assert received == []

    def test_stores_last_check_date_after_reply(self, settings: Settings):
        checker = self._make_checker(settings, {**VERSION_INFO, "version": VERSION})

        with patch.object(platform, "system", return_value="Windows"):
            checker.check_for_updates()

        stored = settings.value(Settings.Key.LAST_UPDATE_CHECK, "")
        assert stored != ""
        datetime.fromisoformat(stored)  # should not raise

    def test_stores_available_version_when_update_found(self, settings: Settings):
        checker = self._make_checker(settings, VERSION_INFO)

        with patch.object(platform, "system", return_value="Windows"), \
             patch("buzz.update_checker.VERSION", "1.0.0"):
            checker.check_for_updates()

        assert settings.value(Settings.Key.UPDATE_AVAILABLE_VERSION, "") == "99.0.0"

    def test_clears_available_version_when_up_to_date(self, settings: Settings):
        settings.set_value(Settings.Key.UPDATE_AVAILABLE_VERSION, "99.0.0")
        checker = self._make_checker(settings, {**VERSION_INFO, "version": VERSION})

        with patch.object(platform, "system", return_value="Windows"):
            checker.check_for_updates()

        assert settings.value(Settings.Key.UPDATE_AVAILABLE_VERSION, "") == ""
