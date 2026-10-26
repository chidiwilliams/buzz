import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QSystemTrayIcon

from buzz.settings.settings import Settings
from buzz.widgets.preferences_dialog import general_preferences_widget


@pytest.fixture
def tray_preferences(qtbot, tmp_path, mocker):
    settings = Settings.__new__(Settings)
    settings.settings = QSettings(
        str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat
    )
    settings_factory = mocker.patch.object(
        general_preferences_widget, "Settings", return_value=settings
    )
    settings_factory.Key = Settings.Key
    mocker.patch.object(general_preferences_widget, "get_password", return_value="")
    available = mocker.patch.object(
        QSystemTrayIcon, "isSystemTrayAvailable", return_value=True
    )
    return settings, available


def test_tray_preferences_default_off_and_save_independently(tray_preferences, qtbot):
    settings, _ = tray_preferences
    widget = general_preferences_widget.GeneralPreferencesWidget()
    qtbot.addWidget(widget)
    assert not widget.minimize_to_tray_checkbox.isChecked()
    assert not widget.close_to_tray_checkbox.isChecked()
    widget.minimize_to_tray_checkbox.click()
    assert settings.value(Settings.Key.MINIMIZE_TO_TRAY, False)
    assert not settings.value(Settings.Key.CLOSE_TO_TRAY, False)
    widget.close_to_tray_checkbox.click()
    assert settings.value(Settings.Key.CLOSE_TO_TRAY, False)
    widget.minimize_to_tray_checkbox.click()
    assert not settings.value(Settings.Key.MINIMIZE_TO_TRAY, True)
    assert settings.value(Settings.Key.CLOSE_TO_TRAY, False)


def test_saved_tray_preferences_are_loaded(tray_preferences, qtbot):
    settings, _ = tray_preferences
    settings.set_value(Settings.Key.MINIMIZE_TO_TRAY, True)
    settings.set_value(Settings.Key.CLOSE_TO_TRAY, True)
    widget = general_preferences_widget.GeneralPreferencesWidget()
    qtbot.addWidget(widget)
    assert widget.minimize_to_tray_checkbox.isChecked()
    assert widget.close_to_tray_checkbox.isChecked()


def test_tray_preferences_are_disabled_without_a_system_tray(tray_preferences, qtbot):
    settings, available = tray_preferences
    available.return_value = False
    widget = general_preferences_widget.GeneralPreferencesWidget()
    qtbot.addWidget(widget)
    assert not widget.minimize_to_tray_checkbox.isEnabled()
    assert not widget.close_to_tray_checkbox.isEnabled()
    assert not settings.value(Settings.Key.MINIMIZE_TO_TRAY, False)
    assert not settings.value(Settings.Key.CLOSE_TO_TRAY, False)
