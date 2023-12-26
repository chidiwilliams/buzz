import webbrowser
from typing import Dict, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar, QWidget

from buzz.locale import _
from buzz.settings.settings import APP_NAME
from buzz.settings.shortcut import Shortcut
from buzz.widgets.about_dialog import AboutDialog
from buzz.widgets.preferences_dialog.models.preferences import Preferences
from buzz.widgets.preferences_dialog.preferences_dialog import (
    PreferencesDialog,
)


class MenuBar(QMenuBar):
    import_action_triggered = pyqtSignal()
    shortcuts_changed = pyqtSignal(dict)
    openai_api_key_changed = pyqtSignal(str)
    default_export_file_name_changed = pyqtSignal(str)
    preferences_changed = pyqtSignal(Preferences)
    preferences_dialog: Optional[PreferencesDialog] = None

    def __init__(
        self,
        shortcuts: Dict[str, str],
        default_export_file_name: str,
        preferences: Preferences,
        parent: QWidget,
    ):
        super().__init__(parent)

        self.shortcuts = shortcuts
        self.default_export_file_name = default_export_file_name
        self.preferences = preferences

        self.import_action = QAction(_("Import Media File..."), self)
        self.import_action.triggered.connect(self.on_import_action_triggered)

        about_action = QAction(f'{_("About")} {APP_NAME}', self)
        about_action.triggered.connect(self.on_about_action_triggered)

        self.preferences_action = QAction(_("Preferences..."), self)
        self.preferences_action.triggered.connect(self.on_preferences_action_triggered)

        help_action = QAction(f'{_("Help")}', self)
        help_action.triggered.connect(self.on_help_action_triggered)

        self.set_shortcuts(shortcuts)

        file_menu = self.addMenu(_("File"))
        file_menu.addAction(self.import_action)

        help_menu = self.addMenu(_("Help"))
        help_menu.addAction(about_action)
        help_menu.addAction(help_action)
        help_menu.addAction(self.preferences_action)

    def on_import_action_triggered(self):
        self.import_action_triggered.emit()

    def on_about_action_triggered(self):
        about_dialog = AboutDialog(parent=self)
        about_dialog.open()

    def on_preferences_action_triggered(self):
        preferences_dialog = PreferencesDialog(
            shortcuts=self.shortcuts,
            default_export_file_name=self.default_export_file_name,
            preferences=self.preferences,
            parent=self,
        )
        preferences_dialog.shortcuts_changed.connect(self.shortcuts_changed)
        preferences_dialog.openai_api_key_changed.connect(self.openai_api_key_changed)
        preferences_dialog.default_export_file_name_changed.connect(
            self.default_export_file_name_changed
        )
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

    def set_shortcuts(self, shortcuts: Dict[str, str]):
        self.shortcuts = shortcuts

        self.import_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.OPEN_IMPORT_WINDOW.name])
        )
        self.preferences_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.OPEN_PREFERENCES_WINDOW.name])
        )
