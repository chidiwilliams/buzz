from typing import Dict, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QWidget, QVBoxLayout, QTabWidget, QDialogButtonBox

from buzz.locale import _
from buzz.widgets.preferences_dialog.general_preferences_widget import (
    GeneralPreferencesWidget,
)
from buzz.widgets.preferences_dialog.models_preferences_widget import (
    ModelsPreferencesWidget,
)
from buzz.widgets.preferences_dialog.shortcuts_editor_preferences_widget import (
    ShortcutsEditorPreferencesWidget,
)


class PreferencesDialog(QDialog):
    shortcuts_changed = pyqtSignal(dict)
    openai_api_key_changed = pyqtSignal(str)
    default_export_file_name_changed = pyqtSignal(str)

    def __init__(
        self,
        shortcuts: Dict[str, str],
        default_export_file_name: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Preferences")

        layout = QVBoxLayout(self)
        tab_widget = QTabWidget(self)

        general_tab_widget = GeneralPreferencesWidget(
            default_export_file_name=default_export_file_name, parent=self
        )
        general_tab_widget.openai_api_key_changed.connect(self.openai_api_key_changed)
        general_tab_widget.default_export_file_name_changed.connect(
            self.default_export_file_name_changed
        )
        tab_widget.addTab(general_tab_widget, _("General"))

        models_tab_widget = ModelsPreferencesWidget(parent=self)
        tab_widget.addTab(models_tab_widget, _("Models"))

        shortcuts_table_widget = ShortcutsEditorPreferencesWidget(shortcuts, self)
        shortcuts_table_widget.shortcuts_changed.connect(self.shortcuts_changed)
        tab_widget.addTab(shortcuts_table_widget, _("Shortcuts"))

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton(QDialogButtonBox.StandardButton.Ok), self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(tab_widget)
        layout.addWidget(button_box)

        self.setLayout(layout)

        self.setFixedSize(self.sizeHint())
