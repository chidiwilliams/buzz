from typing import Optional, Dict

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QWidget, QFormLayout, QPushButton

from buzz.settings.shortcut import Shortcut
from buzz.widgets.sequence_edit import SequenceEdit


class ShortcutsEditorPreferencesWidget(QWidget):
    shortcuts_changed = pyqtSignal(dict)

    def __init__(self, shortcuts: Dict[str, str], parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.shortcuts = shortcuts

        self.layout = QFormLayout(self)
        for shortcut in Shortcut:
            sequence_edit = SequenceEdit(shortcuts.get(shortcut.name, ""), self)
            sequence_edit.keySequenceChanged.connect(
                self.get_key_sequence_changed(shortcut.name)
            )
            self.layout.addRow(shortcut.description, sequence_edit)

        reset_to_defaults_button = QPushButton("Reset to Defaults", self)
        reset_to_defaults_button.setDefault(False)
        reset_to_defaults_button.setAutoDefault(False)
        reset_to_defaults_button.clicked.connect(self.reset_to_defaults)

        self.layout.addWidget(reset_to_defaults_button)

    def get_key_sequence_changed(self, shortcut_name: str):
        def key_sequence_changed(sequence: QKeySequence):
            self.shortcuts[shortcut_name] = sequence.toString()
            self.shortcuts_changed.emit(self.shortcuts)

        return key_sequence_changed

    def reset_to_defaults(self):
        self.shortcuts = Shortcut.get_default_shortcuts()

        for i, shortcut in enumerate(Shortcut):
            sequence_edit = self.layout.itemAt(
                i, QFormLayout.ItemRole.FieldRole
            ).widget()
            assert isinstance(sequence_edit, SequenceEdit)
            sequence_edit.setKeySequence(QKeySequence(self.shortcuts[shortcut.name]))

        self.shortcuts_changed.emit(self.shortcuts)
