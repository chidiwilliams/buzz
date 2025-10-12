from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QPushButton, QLabel
from pytestqt.qtbot import QtBot

from buzz.locale import _
from buzz.widgets.preferences_dialog.shortcuts_editor_preferences_widget import (
    ShortcutsEditorPreferencesWidget,
)
from buzz.widgets.sequence_edit import SequenceEdit


class TestShortcutsEditorWidget:
    def test_should_update_shortcuts(self, qtbot: QtBot, shortcuts):
        widget = ShortcutsEditorPreferencesWidget(shortcuts=shortcuts)
        qtbot.add_widget(widget)

        sequence_edit = widget.findChild(SequenceEdit)
        assert sequence_edit.keySequence().toString() == "Ctrl+R"
        with qtbot.wait_signal(widget.shortcuts_changed, timeout=1000):
            sequence_edit.setKeySequence("Ctrl+Shift+R")

    def test_should_reset_to_defaults(self, qtbot, shortcuts):
        widget = ShortcutsEditorPreferencesWidget(shortcuts=shortcuts)
        qtbot.add_widget(widget)

        reset_button = widget.findChild(QPushButton)
        assert isinstance(reset_button, QPushButton)
        reset_button.click()

        labels = widget.findChildren(QLabel)
        sequence_edits = widget.findChildren(SequenceEdit)

        expected = (
            (_("Open Record Window"), "Ctrl+R"),
            (_("Import File"), "Ctrl+O"),
            (_("Import URL"), "Ctrl+U"),
            (_("Open Preferences Window"), "Ctrl+,"),
            (_("View Transcript Text"), "Ctrl+E"),
            (_("View Transcript Translation"), "Ctrl+L"),
            (_("View Transcript Timestamps"), "Ctrl+T"),
            (_("Search Transcript"), "Ctrl+F"),
            (_("Scroll to Current Text"), "Ctrl+G"),
            (_("Play/Pause Audio"), "Ctrl+P"),
            (_("Replay Current Segment"), "Ctrl+Shift+P"),
            (_("Toggle Playback Controls"), "Ctrl+Alt+P"),
            (_("Decrease Segment Start Time"), "Ctrl+Left"),
            (_("Increase Segment Start Time"), "Ctrl+Right"),
            (_("Decrease Segment End Time"), "Ctrl+Shift+Left"),
            (_("Increase Segment End Time"), "Ctrl+Shift+Right"),
            (_("Clear History"), "Ctrl+S"),
            (_("Cancel Transcription"), "Ctrl+X"),
        )

        for i, (label, sequence_edit) in enumerate(zip(labels, sequence_edits)):
            assert isinstance(label, QLabel)
            assert isinstance(sequence_edit, SequenceEdit)
            assert label.text() == expected[i][0]
            assert sequence_edit.keySequence().toString() == expected[i][1]


class TestSequenceEdit:
    def test_should_ignore_modifier_only_keys(self, qtbot: QtBot):
        sequence_edit = SequenceEdit("")
        qtbot.add_widget(sequence_edit)

        # Test that pressing only modifier keys doesn't record anything
        modifier_keys = [
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ]

        for key in modifier_keys:
            event = QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            sequence_edit.keyPressEvent(event)
            assert sequence_edit.keySequence().toString() == ""

    def test_should_record_key_combination(self, qtbot: QtBot):
        sequence_edit = SequenceEdit("")
        qtbot.add_widget(sequence_edit)

        # Test that pressing a key combination is recorded
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        sequence_edit.keyPressEvent(event)
        assert sequence_edit.keySequence().toString() == "Ctrl+A"

    def test_should_propagate_escape_to_parent(self, qtbot: QtBot):
        from PyQt6.QtWidgets import QWidget

        class ParentWidget(QWidget):
            def __init__(self):
                super().__init__()
                self.escape_pressed = False

            def keyPressEvent(self, event: QKeyEvent) -> None:
                if event.key() == Qt.Key.Key_Escape:
                    self.escape_pressed = True

        parent = ParentWidget()
        qtbot.add_widget(parent)
        sequence_edit = SequenceEdit("", parent)

        # Test that Escape key is propagated to parent
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        sequence_edit.keyPressEvent(event)

        assert parent.escape_pressed
        # Escape key should not be recorded in the sequence
        assert sequence_edit.keySequence().toString() == ""
