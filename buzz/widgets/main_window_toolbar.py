from typing import Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QWidget

from buzz.action import Action
from buzz.locale import _
from buzz.settings.shortcut import Shortcut
from buzz.settings.shortcuts import Shortcuts
from buzz.widgets.icon import Icon
from buzz.widgets.icon import (
    RECORD_ICON_PATH,
    ADD_ICON_PATH,
    URL_ICON_PATH,
    EXPAND_ICON_PATH,
    CANCEL_ICON_PATH,
    TRASH_ICON_PATH,
)
from buzz.widgets.recording_transcriber_widget import RecordingTranscriberWidget
from buzz.widgets.toolbar import ToolBar


class MainWindowToolbar(ToolBar):
    new_transcription_action_triggered: pyqtSignal
    new_url_transcription_action_triggered: pyqtSignal
    open_transcript_action_triggered: pyqtSignal
    clear_history_action_triggered: pyqtSignal
    ICON_LIGHT_THEME_BACKGROUND = "#555"
    ICON_DARK_THEME_BACKGROUND = "#AAA"

    def __init__(self, shortcuts: Shortcuts, parent: Optional[QWidget]):
        super().__init__(parent)

        self.shortcuts = shortcuts

        self.record_action = Action(Icon(RECORD_ICON_PATH, self), _("Record"), self)
        self.record_action.triggered.connect(self.on_record_action_triggered)

        # Note: Changes to "New File Transcription" need to be reflected
        # also in tests/widgets/main_window_test.py
        self.new_transcription_action = Action(
            Icon(ADD_ICON_PATH, self), _("New File Transcription"), self
        )
        self.new_transcription_action_triggered = (
            self.new_transcription_action.triggered
        )

        self.new_url_transcription_action = Action(
            Icon(URL_ICON_PATH, self), _("New URL Transcription"), self
        )
        self.new_url_transcription_action_triggered = (
            self.new_url_transcription_action.triggered
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

        self.reset_shortcuts()

        self.addAction(self.record_action)
        self.addSeparator()
        self.addActions(
            [
                self.new_transcription_action,
                self.new_url_transcription_action,
                self.open_transcript_action,
                self.stop_transcription_action,
                self.clear_history_action,
            ]
        )
        self.setMovable(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

    def reset_shortcuts(self):
        self.record_action.setShortcut(
            QKeySequence.fromString(self.shortcuts.get(Shortcut.OPEN_RECORD_WINDOW))
        )
        self.new_transcription_action.setShortcut(
            QKeySequence.fromString(self.shortcuts.get(Shortcut.OPEN_IMPORT_WINDOW))
        )
        self.new_url_transcription_action.setShortcut(
            QKeySequence.fromString(self.shortcuts.get(Shortcut.OPEN_IMPORT_URL_WINDOW))
        )
        self.stop_transcription_action.setShortcut(
            QKeySequence.fromString(self.shortcuts.get(Shortcut.STOP_TRANSCRIPTION))
        )
        self.clear_history_action.setShortcut(
            QKeySequence.fromString(self.shortcuts.get(Shortcut.CLEAR_HISTORY))
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
