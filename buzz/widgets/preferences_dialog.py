from typing import Dict, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QWidget, QVBoxLayout, QTabWidget, QDialogButtonBox

from buzz.gui import _
from buzz.widgets.shortcuts_editor_widget import ShortcutsEditorWidget


class PreferencesDialog(QDialog):
    shortcuts_changed = pyqtSignal(dict)

    def __init__(self, shortcuts: Dict[str, str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle('Preferences')

        layout = QVBoxLayout(self)
        tab_widget = QTabWidget(self)

        shortcuts_table_widget = ShortcutsEditorWidget(shortcuts, self)
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
