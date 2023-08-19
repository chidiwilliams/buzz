from typing import Dict, Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QWidget

from buzz.action import Action
from buzz.widgets.icon import (
    RECORD_ICON_PATH,
    ADD_ICON_PATH,
    EXPAND_ICON_PATH,
    CANCEL_ICON_PATH,
    TRASH_ICON_PATH,
)
from buzz.locale import _
from buzz.settings.shortcut import Shortcut
from buzz.widgets.icon import Icon
from buzz.widgets.recording_transcriber_widget import RecordingTranscriberWidget
from buzz.widgets.toolbar import ToolBar


class MainWindowToolbar(ToolBar):
    new_transcription_action_triggered: pyqtSignal
    open_transcript_action_triggered: pyqtSignal
    clear_history_action_triggered: pyqtSignal
    ICON_LIGHT_THEME_BACKGROUND = "#555"
    ICON_DARK_THEME_BACKGROUND = "#AAA"

    def __init__(self, shortcuts: Dict[str, str], parent: Optional[QWidget]):
        super().__init__(parent)

        self.record_action = Action(Icon(RECORD_ICON_PATH, self), _("Record"), self)
        self.record_action.triggered.connect(self.on_record_action_triggered)

        self.new_transcription_action = Action(
            Icon(ADD_ICON_PATH, self), _("New Transcription"), self
        )
        self.new_transcription_action_triggered = (
            self.new_transcription_action.triggered
        )

        self.open_transcript_action = Action(
            Icon(EXPAND_ICON_PATH, self), _("Open Transcript"), self
        )
        self.open_transcript_action_triggered = self.open_transcript_action.triggered
        self.open_transcript_action.setDisabled(True)

        self.stop_transcription_action = Action(
            Icon(CANCEL_ICON_PATH, self), _("Cancel Transcription"), self
        )
        self.stop_transcription_action_triggered = (
            self.stop_transcription_action.triggered
        )
        self.stop_transcription_action.setDisabled(True)

        self.clear_history_action = Action(
            Icon(TRASH_ICON_PATH, self), _("Clear History"), self
        )
        self.clear_history_action_triggered = self.clear_history_action.triggered
        self.clear_history_action.setDisabled(True)

        self.set_shortcuts(shortcuts)

        self.addAction(self.record_action)
        self.addSeparator()
        self.addActions(
            [
                self.new_transcription_action,
                self.open_transcript_action,
                self.stop_transcription_action,
                self.clear_history_action,
            ]
        )
        self.setMovable(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

    def set_shortcuts(self, shortcuts: Dict[str, str]):
        self.record_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.OPEN_RECORD_WINDOW.name])
        )
        self.new_transcription_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.OPEN_IMPORT_WINDOW.name])
        )
        self.open_transcript_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.OPEN_TRANSCRIPT_EDITOR.name])
        )
        self.stop_transcription_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.STOP_TRANSCRIPTION.name])
        )
        self.clear_history_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.CLEAR_HISTORY.name])
        )

    def on_record_action_triggered(self):
        recording_transcriber_window = RecordingTranscriberWidget(
            self, flags=Qt.WindowType.Window
        )
        recording_transcriber_window.show()

    def set_stop_transcription_action_enabled(self, enabled: bool):
        self.stop_transcription_action.setEnabled(enabled)

    def set_open_transcript_action_enabled(self, enabled: bool):
        self.open_transcript_action.setEnabled(enabled)

    def set_clear_history_action_enabled(self, enabled: bool):
        self.clear_history_action.setEnabled(enabled)
