import webbrowser
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar, QWidget

from buzz.locale import _
from buzz.settings.settings import APP_NAME
from buzz.settings.shortcut import Shortcut
from buzz.settings.shortcuts import Shortcuts
from buzz.widgets.about_dialog import AboutDialog
from buzz.widgets.preferences_dialog.models.preferences import Preferences
from buzz.widgets.preferences_dialog.preferences_dialog import (
    PreferencesDialog,
)


class MenuBar(QMenuBar):
    import_action_triggered = pyqtSignal()
    import_url_action_triggered = pyqtSignal()
    shortcuts_changed = pyqtSignal()
    openai_api_key_changed = pyqtSignal(str)
    preferences_changed = pyqtSignal(Preferences)
    preferences_dialog: Optional[PreferencesDialog] = None

    def __init__(
        self,
        shortcuts: Shortcuts,
        preferences: Preferences,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.shortcuts = shortcuts
        self.preferences = preferences

        self.import_action = QAction(_("Import File..."), self)
        self.import_action.triggered.connect(self.import_action_triggered)

        self.import_url_action = QAction(_("Import URL..."), self)
        self.import_url_action.triggered.connect(self.import_url_action_triggered)

        about_label = _("About")
        about_action = QAction(f'{about_label} {APP_NAME}', self)
        about_action.triggered.connect(self.on_about_action_triggered)

        self.preferences_action = QAction(_("Preferences..."), self)
        self.preferences_action.triggered.connect(self.on_preferences_action_triggered)

        help_label = _("Help")
        help_action = QAction(f'{help_label}', self)
        help_action.triggered.connect(self.on_help_action_triggered)

        self.reset_shortcuts()

        file_menu = self.addMenu(_("File"))
        file_menu.addAction(self.import_action)
        file_menu.addAction(self.import_url_action)

        help_menu = self.addMenu(_("Help"))
        help_menu.addAction(about_action)
        help_menu.addAction(help_action)
        help_menu.addAction(self.preferences_action)

    def on_about_action_triggered(self):
        about_dialog = AboutDialog(parent=self)
        about_dialog.open()

    def on_preferences_action_triggered(self):
        preferences_dialog = PreferencesDialog(
            shortcuts=self.shortcuts,
            preferences=self.preferences,
            parent=self,
        )
        preferences_dialog.shortcuts_changed.connect(self.shortcuts_changed)
        preferences_dialog.openai_api_key_changed.connect(self.openai_api_key_changed)
        preferences_dialog.finished.connect(self.on_preferences_dialog_finished)
        preferences_dialog.open()

        self.preferences_dialog = preferences_dialog

    def on_preferences_dialog_finished(self, result):
        if result == self.preferences_dialog.DialogCode.Accepted:
            updated_preferences = self.preferences_dialog.updated_preferences
            self.preferences = updated_preferences
            self.preferences_changed.emit(updated_preferences)

    def on_help_action_triggered(self):
        webbrowser.open("https://chidiwilliams.github.io/buzz/docs")

    def reset_shortcuts(self):
        self.import_action.setShortcut(
            QKeySequence.fromString(self.shortcuts.get(Shortcut.OPEN_IMPORT_WINDOW))
        )
        self.import_url_action.setShortcut(
            QKeySequence.fromString(self.shortcuts.get(Shortcut.OPEN_IMPORT_URL_WINDOW))
        )
        self.preferences_action.setShortcut(
            QKeySequence.fromString(
                self.shortcuts.get(Shortcut.OPEN_PREFERENCES_WINDOW)
            )
        )
