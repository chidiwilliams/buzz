import platform
from typing import Optional, Dict

from PyQt6 import QtGui
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QKeySequenceEdit, QWidget, QFormLayout, QPushButton

from buzz.settings.shortcut import Shortcut


class ShortcutsEditorWidget(QWidget):
    shortcuts_changed = pyqtSignal(dict)

    def __init__(self, shortcuts: Dict[str, str], parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.shortcuts = shortcuts

        self.layout = QFormLayout(self)
        for shortcut in Shortcut:
            sequence_edit = SequenceEdit(shortcuts[shortcut.name], self)
            sequence_edit.keySequenceChanged.connect(self.get_key_sequence_changed(shortcut.name))
            self.layout.addRow(shortcut.description, sequence_edit)

        reset_to_defaults_button = QPushButton('Reset to Defaults', self)
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
            sequence_edit = self.layout.itemAt(i, QFormLayout.ItemRole.FieldRole).widget()
            assert isinstance(sequence_edit, SequenceEdit)
            sequence_edit.setKeySequence(QKeySequence(self.shortcuts[shortcut.name]))

        self.shortcuts_changed.emit(self.shortcuts)


class SequenceEdit(QKeySequenceEdit):
    def __init__(self, sequence: str, parent: Optional[QWidget] = None):
        super().__init__(sequence, parent)
        self.setClearButtonEnabled(True)
        if platform.system() == 'Darwin':
            self.setStyleSheet('QLineEdit:focus { border: 2px solid #4d90fe; }')

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        # The shortcut editor always focuses on the sequence edit widgets, so we need to
        # manually capture Esc key presses to close the dialog. The downside being that
        # the user can't set a shortcut that contains the Esc key.
        if key == Qt.Key.Key_Escape:
            self.parent().keyPressEvent(event)
            return

        # Ignore pressing *only* modifier keys
        if key == Qt.Key.Key_Control or key == Qt.Key.Key_Shift or key == Qt.Key.Key_Alt or key == Qt.Key.Key_Meta:
            return

        super().keyPressEvent(event)
