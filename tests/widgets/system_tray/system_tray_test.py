from types import SimpleNamespace
import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QMainWindow, QSystemTrayIcon

from buzz.settings.settings import Settings
from buzz.widgets.system_tray import SystemTray


class TrackingWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.close_calls = 0
        self.reject_close = False
        self.controller = None
        pixmap = QPixmap(16, 16)
        pixmap.fill()
        self.setWindowIcon(QIcon(pixmap))

    def closeEvent(self, event):
        if self.reject_close:
            event.ignore()
            return
        self.close_calls += 1
        if self.controller:
            self.controller.shutdown()
        super().closeEvent(event)


@pytest.fixture
def tray(qtbot, tmp_path, mocker):
    settings = Settings.__new__(Settings)
    settings.settings = QSettings(
        str(tmp_path / "tray.ini"), QSettings.Format.IniFormat
    )
    available = mocker.patch.object(
        QSystemTrayIcon, "isSystemTrayAvailable", return_value=True
    )
    window = TrackingWindow()
    qtbot.addWidget(window)
    controller = SystemTray(window, settings)
    window.controller = controller
    window.show()
    yield SimpleNamespace(
        window=window, controller=controller, settings=settings, available=available
    )
    controller.shutdown()
    window.reject_close = False
    window.close()


def enable(tray, key):
    tray.settings.set_value(key, True)
    tray.controller.update_preferences()


def test_default_minimize_and_close_keep_their_existing_behavior(tray, qtbot):
    assert not tray.controller.icon.isVisible()
    tray.window.showMinimized()
    qtbot.waitUntil(tray.window.isMinimized)
    assert tray.window.isVisible()
    assert tray.window.close()
    assert tray.window.close_calls == 1


@pytest.mark.parametrize(
    "reason",
    [
        QSystemTrayIcon.ActivationReason.Trigger,
        QSystemTrayIcon.ActivationReason.DoubleClick,
    ],
)
def test_minimize_hides_and_tray_activation_restores(tray, qtbot, reason):
    enable(tray, Settings.Key.MINIMIZE_TO_TRAY)
    assert tray.controller.icon.isVisible()
    tray.window.showMinimized()
    qtbot.waitUntil(lambda: not tray.window.isVisible())
    assert tray.window.close_calls == 0
    tray.controller.icon.activated.emit(reason)
    assert tray.window.isVisible()
    assert not tray.window.isMinimized()


def test_close_to_tray_keeps_workers_alive_until_quit(tray, qapp, mocker):
    enable(tray, Settings.Key.CLOSE_TO_TRAY)
    quit_app = mocker.patch.object(qapp, "quit")
    assert not tray.window.close()
    assert not tray.window.isVisible()
    assert tray.window.close_calls == 0
    assert not qapp.quitOnLastWindowClosed()
    tray.controller.quit_action.trigger()
    assert tray.window.close_calls == 1
    assert tray.controller.closed
    assert not tray.controller.icon.isVisible()
    quit_app.assert_called_once_with()


def test_minimize_preference_does_not_change_close_behavior(tray):
    enable(tray, Settings.Key.MINIMIZE_TO_TRAY)
    assert tray.window.close()
    assert tray.window.close_calls == 1


def test_close_preference_does_not_change_minimize_behavior(tray, qtbot):
    enable(tray, Settings.Key.CLOSE_TO_TRAY)
    tray.window.showMinimized()
    qtbot.waitUntil(tray.window.isMinimized)
    assert tray.window.isVisible()


def test_missing_tray_preserves_access_and_normal_close(tray, qtbot):
    tray.available.return_value = False
    enable(tray, Settings.Key.MINIMIZE_TO_TRAY)
    enable(tray, Settings.Key.CLOSE_TO_TRAY)
    assert not tray.controller.icon.isVisible()
    tray.window.showMinimized()
    qtbot.waitUntil(tray.window.isMinimized)
    assert tray.window.isVisible()
    assert tray.window.close()
    assert tray.window.close_calls == 1


def test_disabling_tray_restores_a_hidden_window(tray, qapp):
    original_quit_behavior = qapp.quitOnLastWindowClosed()
    enable(tray, Settings.Key.CLOSE_TO_TRAY)
    tray.window.close()
    tray.settings.set_value(Settings.Key.CLOSE_TO_TRAY, False)
    tray.controller.update_preferences()
    assert tray.window.isVisible()
    assert not tray.controller.icon.isVisible()
    assert qapp.quitOnLastWindowClosed() == original_quit_behavior


def test_quit_respects_a_rejected_close(tray, qapp, mocker):
    enable(tray, Settings.Key.CLOSE_TO_TRAY)
    quit_app = mocker.patch.object(qapp, "quit")
    tray.window.reject_close = True
    tray.controller.quit()
    assert not tray.controller.quitting
    assert not tray.controller.closed
    assert tray.window.isVisible()
    assert tray.controller.icon.isVisible()
    quit_app.assert_not_called()


def test_application_quit_closes_a_hidden_window_and_cleans_up(tray):
    enable(tray, Settings.Key.CLOSE_TO_TRAY)
    tray.window.close()
    tray.controller.on_application_quit()
    assert tray.window.close_calls == 1
    assert tray.controller.closed
    assert not tray.controller.icon.isVisible()


def test_restoring_keeps_a_maximized_window_maximized(tray, qtbot):
    enable(tray, Settings.Key.MINIMIZE_TO_TRAY)
    tray.window.showMaximized()
    tray.window.showMinimized()
    qtbot.waitUntil(lambda: not tray.window.isVisible())
    tray.controller.show_action.trigger()
    assert tray.window.isVisible()
    assert tray.window.isMaximized()


@pytest.mark.parametrize(
    "reason",
    [
        QSystemTrayIcon.ActivationReason.Context,
        QSystemTrayIcon.ActivationReason.MiddleClick,
    ],
)
def test_other_tray_activations_leave_the_window_hidden(tray, reason):
    enable(tray, Settings.Key.CLOSE_TO_TRAY)
    tray.window.close()
    tray.controller.icon.activated.emit(reason)
    assert not tray.window.isVisible()


def test_closing_a_secondary_window_keeps_tray_mode_enabled(tray, qapp, qtbot):
    enable(tray, Settings.Key.CLOSE_TO_TRAY)
    tray.window.close()
    secondary = QMainWindow()
    qtbot.addWidget(secondary)
    secondary.show()
    secondary.close()
    assert not qapp.quitOnLastWindowClosed()
    assert tray.controller.icon.isVisible()
    assert not tray.controller.closed
