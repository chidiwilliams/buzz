from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QWidget, QFormLayout, QPushButton

from buzz.locale import _
from buzz.settings.shortcut import Shortcut
from buzz.settings.shortcuts import Shortcuts
from buzz.widgets.sequence_edit import SequenceEdit


class ShortcutsEditorPreferencesWidget(QWidget):
    shortcuts_changed = pyqtSignal()

    def __init__(self, shortcuts: Shortcuts, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.shortcuts = shortcuts

        self.layout = QFormLayout(self)
        for shortcut in Shortcut:
            sequence_edit = SequenceEdit(shortcuts.get(shortcut), self)
            sequence_edit.keySequenceChanged.connect(
                self.get_key_sequence_changed(shortcut)
            )
            self.layout.addRow(shortcut.description, sequence_edit)

        reset_to_defaults_button = QPushButton(_("Reset to Defaults"), self)
        reset_to_defaults_button.setDefault(False)
        reset_to_defaults_button.setAutoDefault(False)
        reset_to_defaults_button.clicked.connect(self.reset_to_defaults)

        self.layout.addWidget(reset_to_defaults_button)

    def get_key_sequence_changed(self, shortcut: Shortcut):
        def key_sequence_changed(sequence: QKeySequence):
            self.shortcuts.set(shortcut, sequence.toString())
            self.shortcuts_changed.emit()

        return key_sequence_changed

    def reset_to_defaults(self):
        self.shortcuts.clear()

        for i, shortcut in enumerate(Shortcut):
            sequence_edit = self.layout.itemAt(
                i, QFormLayout.ItemRole.FieldRole
            ).widget()
            assert isinstance(sequence_edit, SequenceEdit)
            sequence_edit.setKeySequence(QKeySequence(self.shortcuts.get(shortcut)))

        self.shortcuts_changed.emit()
