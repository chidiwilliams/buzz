import platform
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QUndoCommand, QUndoStack, QKeySequence
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QGridLayout,
)

from buzz.action import Action
from buzz.locale import _
from buzz.paths import file_path_as_title
from buzz.transcriber import (
    FileTranscriptionTask,
    Segment,
)
from buzz.widgets.audio_player import AudioPlayer
from buzz.widgets.icon import UndoIcon, RedoIcon
from buzz.widgets.toolbar import ToolBar
from buzz.widgets.transcription_viewer.export_transcription_button import (
    ExportTranscriptionButton,
)
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    TranscriptionSegmentsEditorWidget,
)


class ChangeSegmentTextCommand(QUndoCommand):
    def __init__(
        self,
        table_widget: TranscriptionSegmentsEditorWidget,
        segments: List[Segment],
        segment_index: int,
        segment_text: str,
        task_changed: pyqtSignal,
    ):
        super().__init__()

        self.table_widget = table_widget
        self.segments = segments
        self.segment_index = segment_index
        self.segment_text = segment_text
        self.task_changed = task_changed

        self.previous_segment_text = self.segments[self.segment_index].text

    def undo(self) -> None:
        self.set_segment_text(self.previous_segment_text)

    def redo(self) -> None:
        self.set_segment_text(self.segment_text)

    def set_segment_text(self, text: str):
        # block signals before setting text so it doesn't re-trigger a new UndoCommand
        self.table_widget.blockSignals(True)
        self.table_widget.set_segment_text(self.segment_index, text)
        self.table_widget.blockSignals(False)
        self.segments[self.segment_index].text = text
        self.task_changed.emit()


class TranscriptionViewerWidget(QWidget):
    transcription_task: FileTranscriptionTask
    task_changed = pyqtSignal()

    def __init__(
        self,
        transcription_task: FileTranscriptionTask,
        open_transcription_output=True,
        parent: Optional["QWidget"] = None,
        flags: Qt.WindowType = Qt.WindowType.Widget,
    ) -> None:
        super().__init__(parent, flags)
        self.transcription_task = transcription_task
        self.open_transcription_output = open_transcription_output

        self.setMinimumWidth(800)
        self.setMinimumHeight(500)

        self.setWindowTitle(file_path_as_title(transcription_task.file_path))

        self.undo_stack = QUndoStack()

        undo_action = self.undo_stack.createUndoAction(self, _("Undo"))
        undo_action.setShortcuts(QKeySequence.StandardKey.Undo)
        undo_action.setIcon(UndoIcon(parent=self))
        undo_action.setToolTip(Action.get_tooltip(undo_action))

        redo_action = self.undo_stack.createRedoAction(self, _("Redo"))
        redo_action.setShortcuts(QKeySequence.StandardKey.Redo)
        redo_action.setIcon(RedoIcon(parent=self))
        redo_action.setToolTip(Action.get_tooltip(redo_action))

        toolbar = ToolBar()
        toolbar.addActions([undo_action, redo_action])

        self.table_widget = TranscriptionSegmentsEditorWidget(
            segments=transcription_task.segments, parent=self
        )
        self.table_widget.segment_text_changed.connect(self.on_segment_text_changed)
        self.table_widget.segment_index_selected.connect(self.on_segment_index_selected)

        self.audio_player: Optional[AudioPlayer] = None
        if platform.system() != "Linux":
            self.audio_player = AudioPlayer(file_path=transcription_task.file_path)
            self.audio_player.position_ms_changed.connect(
                self.on_audio_player_position_ms_changed
            )

        self.current_segment_label = QLabel()
        self.current_segment_label.setText("")
        self.current_segment_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        export_button = ExportTranscriptionButton(
            transcription_task=transcription_task, parent=self
        )

        layout = QGridLayout(self)
        layout.setMenuBar(toolbar)
        layout.addWidget(self.table_widget, 0, 0, 1, 2)

        if self.audio_player is not None:
            layout.addWidget(self.audio_player, 1, 0, 1, 1)
        layout.addWidget(export_button, 1, 1, 1, 1)
        layout.addWidget(self.current_segment_label, 2, 0, 1, 2)

        self.setLayout(layout)

    def on_segment_text_changed(self, event: tuple):
        segment_index, segment_text = event
        self.undo_stack.push(
            ChangeSegmentTextCommand(
                table_widget=self.table_widget,
                segments=self.transcription_task.segments,
                segment_index=segment_index,
                segment_text=segment_text,
                task_changed=self.task_changed,
            )
        )

    def on_segment_index_selected(self, index: int):
        selected_segment = self.transcription_task.segments[index]
        if self.audio_player is not None:
            self.audio_player.set_range((selected_segment.start, selected_segment.end))

    def on_audio_player_position_ms_changed(self, position_ms: int) -> None:
        current_segment_index: Optional[int] = next(
            (
                i
                for i, segment in enumerate(self.transcription_task.segments)
                if segment.start <= position_ms < segment.end
            ),
            None,
        )
        if current_segment_index is not None:
            self.current_segment_label.setText(
                self.transcription_task.segments[current_segment_index].text
            )
