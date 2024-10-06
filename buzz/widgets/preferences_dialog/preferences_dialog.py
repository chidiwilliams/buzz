import copy
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QWidget, QVBoxLayout, QTabWidget, QDialogButtonBox

from buzz.locale import _
from buzz.settings.shortcuts import Shortcuts
from buzz.widgets.preferences_dialog.folder_watch_preferences_widget import (
    FolderWatchPreferencesWidget,
)
from buzz.widgets.preferences_dialog.general_preferences_widget import (
    GeneralPreferencesWidget,
)
from buzz.widgets.preferences_dialog.models.folder_watch_preferences import (
    FolderWatchPreferences,
)
from buzz.widgets.preferences_dialog.models.preferences import Preferences
from buzz.widgets.preferences_dialog.models_preferences_widget import (
    ModelsPreferencesWidget,
)
from buzz.widgets.preferences_dialog.shortcuts_editor_preferences_widget import (
    ShortcutsEditorPreferencesWidget,
)


class PreferencesDialog(QDialog):
    shortcuts_changed = pyqtSignal()
    openai_api_key_changed = pyqtSignal(str)
    folder_watch_config_changed = pyqtSignal(FolderWatchPreferences)
    preferences_changed = pyqtSignal(Preferences)

    def __init__(
        self,
        shortcuts: Shortcuts,
        preferences: Preferences,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.updated_preferences = copy.deepcopy(preferences)

        self.setWindowTitle(_("Preferences"))

        layout = QVBoxLayout(self)
        tab_widget = QTabWidget(self)

        general_tab_widget = GeneralPreferencesWidget(parent=self)
        general_tab_widget.openai_api_key_changed.connect(self.openai_api_key_changed)
        tab_widget.addTab(general_tab_widget, _("General"))

        models_tab_widget = ModelsPreferencesWidget(parent=self)
        tab_widget.addTab(models_tab_widget, _("Models"))

        shortcuts_table_widget = ShortcutsEditorPreferencesWidget(shortcuts, self)
        shortcuts_table_widget.shortcuts_changed.connect(self.shortcuts_changed)
        tab_widget.addTab(shortcuts_table_widget, _("Shortcuts"))

        folder_watch_widget = FolderWatchPreferencesWidget(
            config=self.updated_preferences.folder_watch, parent=self
        )
        folder_watch_widget.config_changed.connect(self.folder_watch_config_changed)
        tab_widget.addTab(folder_watch_widget, _("Folder Watch"))

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText(_("Ok"))
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(_("Cancel"))
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(tab_widget)
        layout.addWidget(button_box)

        self.setLayout(layout)

        self.setMinimumHeight(500)
        self.setMinimumWidth(650)
