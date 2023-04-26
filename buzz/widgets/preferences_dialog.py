from typing import Dict, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QWidget, QVBoxLayout, QTabWidget, QDialogButtonBox

from buzz.locale import _
from buzz.store.keyring_store import KeyringStore
from buzz.widgets.general_preferences_widget import GeneralPreferencesWidget
from buzz.widgets.shortcuts_editor_preferences_widget import ShortcutsEditorPreferencesWidget


class PreferencesDialog(QDialog):
    shortcuts_changed = pyqtSignal(dict)
    openai_api_key_changed = pyqtSignal(str)

    def __init__(self, shortcuts: Dict[str, str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle('Preferences')

        layout = QVBoxLayout(self)
        tab_widget = QTabWidget(self)

        general_tab_widget = GeneralPreferencesWidget(parent=self)
        general_tab_widget.openai_api_key_changed.connect(self.openai_api_key_changed)
        tab_widget.addTab(general_tab_widget, _('General'))

        shortcuts_table_widget = ShortcutsEditorPreferencesWidget(shortcuts, self)
        shortcuts_table_widget.shortcuts_changed.connect(self.shortcuts_changed)
        tab_widget.addTab(shortcuts_table_widget, _('Shortcuts'))

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton(
            QDialogButtonBox.StandardButton.Ok), self)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(tab_widget)
        layout.addWidget(button_box)

        self.setLayout(layout)

        self.setFixedSize(self.sizeHint())
