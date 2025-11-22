import enum
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from PyQt6.QtCore import pyqtSignal, Qt, QModelIndex, QItemSelection, QEvent, QRegularExpression, QObject
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtSql import QSqlTableModel, QSqlRecord
from PyQt6.QtGui import QFontMetrics, QTextOption
from PyQt6.QtWidgets import (
    QWidget,
    QTableView,
    QStyledItemDelegate,
    QAbstractItemView,
    QTextEdit,
    QLineEdit,
)

from buzz.locale import _
from buzz.translator import Translator
from buzz.transcriber.file_transcriber import to_timestamp


class Column(enum.Enum):
    ID = 0
    END = enum.auto()
    START = enum.auto()
    TEXT = enum.auto()
    TRANSLATION = enum.auto()
    TRANSCRIPTION_ID = enum.auto()


@dataclass
class ColDef:
    id: str
    header: str
    column: Column
    delegate: Optional[QStyledItemDelegate] = None


def parse_timestamp(timestamp_str: str) -> Optional[int]:
    """Parse timestamp string (HH:MM:SS.mmm) to milliseconds"""
    try:
        # Handle formats like "00:01:23.456" or "1:23.456" or "23.456"
        parts = timestamp_str.strip().split(':')

        if len(parts) == 3:  # HH:MM:SS.mmm
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds_parts = parts[2].split('.')
        elif len(parts) == 2:  # MM:SS.mmm
            hours = 0
            minutes = int(parts[0])
            seconds_parts = parts[1].split('.')
        elif len(parts) == 1:  # SS.mmm
            hours = 0
            minutes = 0
            seconds_parts = parts[0].split('.')
        else:
            return None

        seconds = int(seconds_parts[0])
        milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0

        total_ms = hours * 3600 * 1000 + minutes * 60 * 1000 + seconds * 1000 + milliseconds
        return total_ms
    except (ValueError, IndexError):
        return None


class TimeStampLineEdit(QLineEdit):
    """Custom QLineEdit for timestamp editing with keyboard shortcuts"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._milliseconds = 0

        # Set up validator to only allow digits, colons, and dots
        regex = QRegularExpression(r'^[0-9:.]*$')
        validator = QRegularExpressionValidator(regex, self)
        self.setValidator(validator)

    def set_milliseconds(self, ms: int):
        self._milliseconds = ms
        self.setText(to_timestamp(ms))

    def get_milliseconds(self) -> int:
        parsed = parse_timestamp(self.text())
        if parsed is not None:
            return parsed
        return self._milliseconds

    def keyPressEvent(self, event):
        if event.text() == '+':
            self._milliseconds += 500  # Add 500ms (0.5 seconds)
            self.setText(to_timestamp(self._milliseconds))
            event.accept()
        elif event.text() == '-':
            self._milliseconds = max(0, self._milliseconds - 500)  # Subtract 500ms
            self.setText(to_timestamp(self._milliseconds))
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        # Strip any invalid characters and reformat on focus out
        parsed = parse_timestamp(self.text())
        if parsed is not None:
            self._milliseconds = parsed
            self.setText(to_timestamp(parsed))
        else:
            # If parsing failed, restore the last valid value
            self.setText(to_timestamp(self._milliseconds))
        super().focusOutEvent(event)


class TimeStampDelegate(QStyledItemDelegate):
    def displayText(self, value, locale):
        return to_timestamp(value)


class TimeStampEditorDelegate(QStyledItemDelegate):
    """Delegate for editing timestamps with overlap prevention"""

    timestamp_editing = pyqtSignal(int, int, int)  # Signal: (row, column, new_value_ms)

    def createEditor(self, parent, option, index):
        editor = TimeStampLineEdit(parent)
        # Connect text changed signal to emit live updates
        editor.textChanged.connect(lambda: self.on_editor_text_changed(editor, index))
        return editor

    def on_editor_text_changed(self, editor, index):
        """Emit signal when editor text changes with the current value"""
        new_value_ms = editor.get_milliseconds()
        self.timestamp_editing.emit(index.row(), index.column(), new_value_ms)

    def setEditorData(self, editor, index):
        # Get value in milliseconds from database
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        if value is not None:
            editor.set_milliseconds(value)

    def setModelData(self, editor, model, index):
        # Get value in milliseconds from editor
        new_value_ms = editor.get_milliseconds()
        current_row = index.row()
        column = index.column()

        # Get current segment's start and end
        start_col = Column.START.value
        end_col = Column.END.value

        if column == start_col:
            # Editing START time
            end_time_ms = model.record(current_row).value("end_time")

            if end_time_ms is None:
                logging.warning("End time is None, cannot validate")
                return

            # Validate: start must be less than end
            if new_value_ms >= end_time_ms:
                logging.warning(f"Start time ({new_value_ms}) must be less than end time ({end_time_ms})")
                return

            # Check if new start overlaps with previous segment's end
            if current_row > 0:
                prev_end_time_ms = model.record(current_row - 1).value("end_time")
                if prev_end_time_ms is not None and new_value_ms < prev_end_time_ms:
                    # Update previous segment's end to match new start
                    model.setData(model.index(current_row - 1, end_col), new_value_ms)

        elif column == end_col:
            # Editing END time
            start_time_ms = model.record(current_row).value("start_time")

            if start_time_ms is None:
                logging.warning("Start time is None, cannot validate")
                return

            # Validate: end must be greater than start
            if new_value_ms <= start_time_ms:
                logging.warning(f"End time ({new_value_ms}) must be greater than start time ({start_time_ms})")
                return

            # Check if new end overlaps with next segment's start
            if current_row < model.rowCount() - 1:
                next_start_time_ms = model.record(current_row + 1).value("start_time")
                if next_start_time_ms is not None and new_value_ms > next_start_time_ms:
                    # Update next segment's start to match new end
                    model.setData(model.index(current_row + 1, start_col), new_value_ms)

        # Set the new value
        model.setData(index, new_value_ms)

    def displayText(self, value, locale):
        return to_timestamp(value)


class CustomTextEdit(QTextEdit):
    """Custom QTextEdit that handles Tab/Enter/Esc keys to save and close editor"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event):
        # Tab, Enter, or Esc: save and close editor
        if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            # Close the editor which will trigger setModelData to save
            self.clearFocus()
            event.accept()
        else:
            super().keyPressEvent(event)


class WordWrapDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = CustomTextEdit(parent)
        editor.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        editor.setAcceptRichText(False)
        editor.setTabChangesFocus(True)

        return editor

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText())


class TranscriptionSegmentModel(QSqlTableModel):
    def __init__(self, transcription_id: UUID):
        super().__init__()
        self.setTable("transcription_segment")
        self.setEditStrategy(QSqlTableModel.EditStrategy.OnFieldChange)
        self.setFilter(f"transcription_id = '{transcription_id}'")


class TranscriptionSegmentsEditorWidget(QTableView):
    PARENT_PADDINGS = 40
    segment_selected = pyqtSignal(QSqlRecord)
    timestamp_being_edited = pyqtSignal(int, int, int)  # Signal: (row, column, new_value_ms)

    def keyPressEvent(self, event):
        # Allow Enter/Return to trigger editing
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            current_index = self.currentIndex()
            if current_index.isValid() and not self.state() == QAbstractItemView.State.EditingState:
                self.edit(current_index)
                event.accept()
                return
        super().keyPressEvent(event)

    def __init__(
            self,
            transcription_id: UUID,
            translator: Translator,
            parent: Optional[QWidget]
    ):
        super().__init__(parent)

        self._last_highlighted_row = -1
        self.translator = translator
        self.translator.translation.connect(self.update_translation)

        model = TranscriptionSegmentModel(transcription_id=transcription_id)
        self.setModel(model)

        timestamp_editor_delegate = TimeStampEditorDelegate()
        # Connect delegate's signal to widget's signal
        timestamp_editor_delegate.timestamp_editing.connect(self.timestamp_being_edited.emit)

        word_wrap_delegate = WordWrapDelegate()

        self.column_definitions: list[ColDef] = [
            ColDef("start", _("Start"), Column.START, delegate=timestamp_editor_delegate),
            ColDef("end", _("End"), Column.END, delegate=timestamp_editor_delegate),
            ColDef("text", _("Text"), Column.TEXT, delegate=word_wrap_delegate),
            ColDef("translation", _("Translation"), Column.TRANSLATION, delegate=word_wrap_delegate),
        ]

        for i in range(model.columnCount()):
            self.hideColumn(i)

        for definition in self.column_definitions:
            model.setHeaderData(
                definition.column.value,
                Qt.Orientation.Horizontal,
                definition.header,
            )
            self.showColumn(definition.column.value)
            if definition.delegate is not None:
                self.setItemDelegateForColumn(
                    definition.column.value, definition.delegate
                )

        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.EditKeyPressed |
            QAbstractItemView.EditTrigger.DoubleClicked
        )
        self.selectionModel().selectionChanged.connect(self.on_selection_changed)
        model.select()
        model.rowsInserted.connect(self.init_row_height)

        self.has_translations = self.has_non_empty_translation()

        # Show start before end
        self.horizontalHeader().swapSections(1, 2)

        self.init_row_height()

        self.setColumnWidth(Column.START.value, 120)
        self.setColumnWidth(Column.END.value, 120)

        self.setWordWrap(True)

    def init_row_height(self):
        font_metrics = QFontMetrics(self.font())
        max_row_height = font_metrics.height() * 4
        row_count = self.model().rowCount()

        for row in range(row_count):
            self.setRowHeight(row, max_row_height)

    def has_non_empty_translation(self) -> bool:
        for i in range(self.model().rowCount()):
            if self.model().record(i).value("translation").strip():
                return True
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if not self.has_translations:
            self.hideColumn(Column.TRANSLATION.value)
        else:
            self.showColumn(Column.TRANSLATION.value)

        text_column_count = 2 if self.has_translations else 1

        time_column_widths = self.columnWidth(Column.START.value) + self.columnWidth(Column.END.value)
        text_column_width = (
            int((self.parent().width() - self.PARENT_PADDINGS - time_column_widths) / text_column_count))

        self.setColumnWidth(Column.TEXT.value, text_column_width)
        self.setColumnWidth(Column.TRANSLATION.value, text_column_width)

    def update_translation(self, translation: str, segment_id: Optional[int] = None):
        self.has_translations = True
        self.resizeEvent(None)

        for row in range(self.model().rowCount()):
            if self.model().record(row).value("id") == segment_id:
                self.model().setData(self.model().index(row, Column.TRANSLATION.value), translation)
                break

    def on_selection_changed(
        self, selected: QItemSelection, _deselected: QItemSelection
    ):
        if selected.indexes():
            self.segment_selected.emit(self.segment(selected.indexes()[0]))

    def segment(self, index: QModelIndex) -> QSqlRecord:
        return self.model().record(index.row())

    def segments(self) -> list[QSqlRecord]:
        return [self.model().record(i) for i in range(self.model().rowCount())]

    def highlight_and_scroll_to_row(self, row_index: int):
        """Highlight a specific row and scroll it into view"""
        if 0 <= row_index < self.model().rowCount():
            # Only set focus if we're actually moving to a different row to avoid audio crackling
            if self._last_highlighted_row != row_index:
                self.setFocus()
                self._last_highlighted_row = row_index
            
            # Select the row
            self.selectRow(row_index)
            # Scroll to the row with better positioning
            model_index = self.model().index(row_index, 0)
            self.scrollTo(model_index, QAbstractItemView.ScrollHint.PositionAtCenter)
