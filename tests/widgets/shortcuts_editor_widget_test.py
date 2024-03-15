from PyQt6.QtWidgets import QPushButton, QLabel

from buzz.widgets.preferences_dialog.shortcuts_editor_preferences_widget import (
    ShortcutsEditorPreferencesWidget,
)
from buzz.widgets.sequence_edit import SequenceEdit


class TestShortcutsEditorWidget:
    def test_should_reset_to_defaults(self, qtbot, shortcuts):
        widget = ShortcutsEditorPreferencesWidget(shortcuts=shortcuts)
        qtbot.add_widget(widget)

        reset_button = widget.findChild(QPushButton)
        assert isinstance(reset_button, QPushButton)
        reset_button.click()

        labels = widget.findChildren(QLabel)
        sequence_edits = widget.findChildren(SequenceEdit)

        expected = (
            ("Open Record Window", "Ctrl+R"),
            ("Import File", "Ctrl+O"),
            ("Import URL", "Ctrl+U"),
            ("Open Preferences Window", "Ctrl+,"),
            ("View Transcript Text", "Ctrl+E"),
            ("View Transcript Timestamps", "Ctrl+T"),
            ("Clear History", "Ctrl+S"),
            ("Cancel Transcription", "Ctrl+X"),
        )

        for i, (label, sequence_edit) in enumerate(zip(labels, sequence_edits)):
            assert isinstance(label, QLabel)
            assert isinstance(sequence_edit, SequenceEdit)
            assert label.text() == expected[i][0]
            assert sequence_edit.keySequence().toString() == expected[i][1]
