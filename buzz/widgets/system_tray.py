from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

from buzz.locale import _
from buzz.settings.settings import APP_NAME, Settings


class SystemTray(QObject):
    """Keep the main window available while optional tray mode is enabled."""

    def __init__(self, window: QMainWindow, settings: Settings):
        super().__init__(window)
        self.window = window
        self.settings = settings
        self.quitting = False
        self.closed = False
        self.app = QApplication.instance()
        self.quit_on_last_window_closed = self.app.quitOnLastWindowClosed()

        self.icon = QSystemTrayIcon(window.windowIcon(), self)
        self.icon.setToolTip(APP_NAME)
        self.menu = QMenu(window)
        self.show_action = self.menu.addAction(_("Show Buzz"))
        self.show_action.triggered.connect(self.restore_window)
        self.quit_action = self.menu.addAction(_("Quit"))
        self.quit_action.triggered.connect(self.quit)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self.on_activated)

        self.window.installEventFilter(self)
        self.app.aboutToQuit.connect(self.on_application_quit)
        self.update_preferences()

    def enabled(self, key: Settings.Key) -> bool:
        return (
            not self.closed
            and not self.quitting
            and self.settings.value(key, False)
            and QSystemTrayIcon.isSystemTrayAvailable()
        )

    def update_preferences(self):
        if self.closed:
            return
        enabled = self.enabled(Settings.Key.MINIMIZE_TO_TRAY) or self.enabled(
            Settings.Key.CLOSE_TO_TRAY
        )
        if enabled:
            self.icon.show()
            # Closing a secondary window must not quit while the main window is hidden.
            self.app.setQuitOnLastWindowClosed(False)
        else:
            if self.icon.isVisible() and not self.window.isVisible():
                self.restore_window()
            self.icon.hide()
            self.app.setQuitOnLastWindowClosed(self.quit_on_last_window_closed)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.window and not self.quitting and not self.closed:
            if event.type() == QEvent.Type.Close:
                self.update_preferences()
                if self.enabled(Settings.Key.CLOSE_TO_TRAY):
                    event.ignore()
                    self.window.hide()
                    return True
            elif event.type() == QEvent.Type.WindowStateChange:
                if self.window.isMinimized() and self.enabled(
                    Settings.Key.MINIMIZE_TO_TRAY
                ):
                    self.update_preferences()
                    QTimer.singleShot(0, self.hide_minimized_window)
        return super().eventFilter(watched, event)

    def hide_minimized_window(self):
        if self.window.isMinimized() and self.enabled(Settings.Key.MINIMIZE_TO_TRAY):
            self.window.hide()

    def restore_window(self):
        # Removing only the minimized flag preserves a previously maximized window.
        self.window.setWindowState(
            self.window.windowState() & ~Qt.WindowState.WindowMinimized
        )
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.restore_window()

    def quit(self):
        self.quitting = True
        # Let MainWindow.closeEvent perform its existing worker/database cleanup.
        if self.window.close():
            self.shutdown()
            self.app.quit()
        else:
            self.quitting = False

    def on_application_quit(self):
        if not self.closed:
            self.quitting = True
            self.window.close()
            self.shutdown()

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        self.icon.hide()
        self.window.removeEventFilter(self)
        self.app.setQuitOnLastWindowClosed(self.quit_on_last_window_closed)
        self.app.aboutToQuit.disconnect(self.on_application_quit)
