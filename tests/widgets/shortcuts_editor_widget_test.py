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
            (_("Clear History"), "Ctrl+S"),
            (_("Cancel Transcription"), "Ctrl+X"),
        )

        for i, (label, sequence_edit) in enumerate(zip(labels, sequence_edits)):
            assert isinstance(label, QLabel)
            assert isinstance(sequence_edit, SequenceEdit)
            assert label.text() == expected[i][0]
            assert sequence_edit.keySequence().toString() == expected[i][1]
