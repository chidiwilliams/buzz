from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QUndoCommand, QUndoStack, QKeySequence, QAction
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QMenu, QPushButton, QVBoxLayout, QFileDialog

from buzz.action import Action
from buzz.assets import get_asset_path
from buzz.paths import file_path_as_title
from buzz.icon import Icon
from buzz.locale import _
from buzz.transcriber import FileTranscriptionTask, Segment, OutputFormat, get_default_output_file_path, write_output
from buzz.widgets.toolbar import ToolBar
from buzz.widgets.transcription_segments_editor_widget import TranscriptionSegmentsEditorWidget


class TranscriptionViewerWidget(QWidget):
    transcription_task: FileTranscriptionTask
    task_changed = pyqtSignal()

    class ChangeSegmentTextCommand(QUndoCommand):
        def __init__(self, table_widget: TranscriptionSegmentsEditorWidget, segments: List[Segment],
                     segment_index: int, segment_text: str, task_changed: pyqtSignal):
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

    def __init__(
            self, transcription_task: FileTranscriptionTask,
            open_transcription_output=True,
            parent: Optional['QWidget'] = None,
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
        undo_action.setIcon(Icon(get_asset_path('assets/undo_FILL0_wght700_GRAD0_opsz48.svg'), self))
        undo_action.setToolTip(Action.get_tooltip(undo_action))

        redo_action = self.undo_stack.createRedoAction(self, _("Redo"))
        redo_action.setShortcuts(QKeySequence.StandardKey.Redo)
        redo_action.setIcon(Icon(get_asset_path('assets/redo_FILL0_wght700_GRAD0_opsz48.svg'), self))
        redo_action.setToolTip(Action.get_tooltip(redo_action))

        toolbar = ToolBar()
        toolbar.addActions([undo_action, redo_action])

        self.table_widget = TranscriptionSegmentsEditorWidget(segments=transcription_task.segments, parent=self)
        self.table_widget.segment_text_changed.connect(self.on_segment_text_changed)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        export_button_menu = QMenu()
        actions = [QAction(text=output_format.value.upper(), parent=self)
                   for output_format in OutputFormat]
        export_button_menu.addActions(actions)

        export_button_menu.triggered.connect(self.on_menu_triggered)

        export_button = QPushButton(self)
        export_button.setText(_('Export'))
        export_button.setMenu(export_button_menu)

        buttons_layout.addWidget(export_button)

        layout = QVBoxLayout(self)
        layout.setMenuBar(toolbar)
        layout.addWidget(self.table_widget)
        layout.addLayout(buttons_layout)

        self.setLayout(layout)

    def on_segment_text_changed(self, event: tuple):
        segment_index, segment_text = event
        self.undo_stack.push(
            self.ChangeSegmentTextCommand(table_widget=self.table_widget, segments=self.transcription_task.segments,
                                          segment_index=segment_index, segment_text=segment_text,
                                          task_changed=self.task_changed))

    def on_menu_triggered(self, action: QAction):
        output_format = OutputFormat[action.text()]

        default_path = get_default_output_file_path(
            task=self.transcription_task.transcription_options.task,
            input_file_path=self.transcription_task.file_path,
            output_format=output_format)

        (output_file_path, nil) = QFileDialog.getSaveFileName(self, _('Save File'), default_path,
                                                              _('Text files') + f' (*.{output_format.value})')

        if output_file_path == '':
            return

        write_output(path=output_file_path, segments=self.transcription_task.segments, output_format=output_format)
