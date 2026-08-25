import enum
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from PyQt6.QtCore import (
    pyqtSignal,
    Qt,
    QModelIndex,
    QItemSelection,
    QRegularExpression,
    QSize,
)
from PyQt6.QtGui import (
    QColor,
    QFontMetrics,
    QIcon,
    QPainter,
    QPixmap,
    QRegularExpressionValidator,
    QTextOption,
)
from PyQt6.QtSql import QSqlTableModel, QSqlRecord
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QTableView,
    QStyledItemDelegate,
    QAbstractItemView,
    QTextEdit,
    QLineEdit,
    QComboBox,
    QInputDialog,
    QMenu,
    QStyle,
    QStyleOptionViewItem,
)

from buzz.locale import _
from buzz.speaker_transcript import SPEAKER_COLORS
from buzz.translator import Translator
from buzz.transcriber.file_transcriber import to_timestamp


class Column(enum.Enum):
    ID = 0
    END = enum.auto()
    START = enum.auto()
    TEXT = enum.auto()
    TRANSLATION = enum.auto()
    TRANSCRIPTION_ID = enum.auto()
    SPEAKER = enum.auto()


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


class SpeakerDelegate(QStyledItemDelegate):
    """Editable speaker selector with a visible, accessible color marker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.speakers: list[str] = []
        self.colors: dict[str, QColor] = {}

    def set_speakers(self, speakers: list[str]):
        self.speakers = speakers
        self.colors = {
            speaker: QColor(SPEAKER_COLORS[index % len(SPEAKER_COLORS)])
            for index, speaker in enumerate(speakers)
        }

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.setEditable(True)
        editor.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        editor.addItem(_("Unassigned"), "")
        for speaker in self.speakers:
            editor.addItem(speaker, speaker)
        editor.setToolTip(
            _("Choose an identified speaker or type a new speaker name.")
        )
        return editor

    def setEditorData(self, editor, index):
        speaker = (index.data(Qt.ItemDataRole.EditRole) or "").strip()
        speaker_index = editor.findData(speaker)
        if speaker_index >= 0:
            editor.setCurrentIndex(speaker_index)
        else:
            editor.setEditText(speaker)

    def setModelData(self, editor, model, index):
        current_index = editor.currentIndex()
        if (
            current_index >= 0
            and editor.currentText() == editor.itemText(current_index)
        ):
            speaker = editor.itemData(current_index) or ""
        else:
            speaker = editor.currentText().strip()
        model.setData(index, speaker)

    def paint(self, painter, option, index):
        speaker = (index.data(Qt.ItemDataRole.EditRole) or "").strip()
        styled_option = QStyleOptionViewItem(option)
        self.initStyleOption(styled_option, index)
        styled_option.text = speaker or _("Unassigned")

        if speaker:
            pixmap = QPixmap(12, 12)
            pixmap.fill(Qt.GlobalColor.transparent)
            icon_painter = QPainter(pixmap)
            icon_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            icon_painter.setBrush(self.colors.get(speaker, QColor(SPEAKER_COLORS[0])))
            icon_painter.setPen(Qt.PenStyle.NoPen)
            icon_painter.drawEllipse(1, 1, 10, 10)
            icon_painter.end()
            styled_option.icon = QIcon(pixmap)
            styled_option.decorationSize = QSize(12, 12)

        style = (
            styled_option.widget.style()
            if styled_option.widget is not None
            else QApplication.style()
        )
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            styled_option,
            painter,
            styled_option.widget,
        )


class TranscriptionSegmentModel(QSqlTableModel):
    def __init__(self, transcription_id: UUID):
        super().__init__()
        self.setTable("transcription_segment")
        self.setEditStrategy(QSqlTableModel.EditStrategy.OnFieldChange)
        self.setFilter(f"transcription_id = '{transcription_id}'")


class TranscriptionSegmentsEditorWidget(QTableView):
    PARENT_PADDINGS = 40
    SPEAKER_COLUMN_WIDTH = 160
    segment_selected = pyqtSignal(QSqlRecord)
    timestamp_being_edited = pyqtSignal(int, int, int)  # Signal: (row, column, new_value_ms)
    speakers_changed = pyqtSignal(list)

    _segments_cache: list[QSqlRecord] | None = None

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
        self._bulk_updating_speakers = False
        self.has_speakers = False
        self.translator = translator
        self.translator.translation.connect(self.update_translation)

        model = TranscriptionSegmentModel(transcription_id=transcription_id)
        self.setModel(model)

        timestamp_editor_delegate = TimeStampEditorDelegate()
        # Connect delegate's signal to widget's signal
        timestamp_editor_delegate.timestamp_editing.connect(self.timestamp_being_edited.emit)

        word_wrap_delegate = WordWrapDelegate()
        self.speaker_delegate = SpeakerDelegate(self)

        self.column_definitions: list[ColDef] = [
            ColDef("start", _("Start"), Column.START, delegate=timestamp_editor_delegate),
            ColDef("end", _("End"), Column.END, delegate=timestamp_editor_delegate),
            ColDef("speaker", _("Speaker"), Column.SPEAKER, delegate=self.speaker_delegate),
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

        model.setHeaderData(
            Column.SPEAKER.value,
            Qt.Orientation.Horizontal,
            _(
                "Double-click to edit. Select multiple rows and right-click "
                "to assign speakers."
            ),
            Qt.ItemDataRole.ToolTipRole,
        )

        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.EditKeyPressed |
            QAbstractItemView.EditTrigger.DoubleClicked
        )
        self.selectionModel().selectionChanged.connect(self.on_selection_changed)
        model.select()
        model.rowsInserted.connect(self.init_row_height)
        model.dataChanged.connect(self._invalidate_segments_cache)
        model.dataChanged.connect(self._on_model_data_changed)
        model.modelReset.connect(self._invalidate_segments_cache)

        self.has_translations = self.has_non_empty_translation()

        # Show start before end
        self.horizontalHeader().swapSections(1, 2)
        self.horizontalHeader().moveSection(
            self.horizontalHeader().visualIndex(Column.SPEAKER.value),
            self.horizontalHeader().visualIndex(Column.TEXT.value),
        )

        self.init_row_height()

        self.setColumnWidth(Column.START.value, 120)
        self.setColumnWidth(Column.END.value, 120)
        self.setColumnWidth(Column.SPEAKER.value, self.SPEAKER_COLUMN_WIDTH)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._refresh_speakers()

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

        fixed_column_widths = (
            self.columnWidth(Column.START.value)
            + self.columnWidth(Column.END.value)
        )
        if self.has_speakers:
            fixed_column_widths += self.columnWidth(Column.SPEAKER.value)
        text_column_width = (
            int((self.parent().width() - self.PARENT_PADDINGS - fixed_column_widths) / text_column_count))

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

    def _fetch_all_rows(self):
        """Ensure all rows are loaded from the database.

        QSqlTableModel fetches rows lazily (256 at a time), so rowCount()
        only reflects rows already loaded. For operations that must see the
        whole transcript (e.g. search), force fetching the remaining rows.
        """
        model = self.model()
        root = QModelIndex()
        while model.canFetchMore(root):
            model.fetchMore(root)

    def _invalidate_segments_cache(self):
        self._segments_cache = None

    def _on_model_data_changed(self, top_left, bottom_right, roles=None):
        if (
            not self._bulk_updating_speakers
            and
            top_left.column() <= Column.SPEAKER.value
            <= bottom_right.column()
        ):
            self._refresh_speakers()

    def speaker_names(self) -> list[str]:
        names = []
        for segment in self.segments():
            speaker = (segment.value("speaker") or "").strip()
            if speaker and speaker not in names:
                names.append(speaker)
        return names

    def _refresh_speakers(self):
        self._invalidate_segments_cache()
        speakers = self.speaker_names()
        self.speaker_delegate.set_speakers(speakers)
        self.has_speakers = bool(speakers)
        self._update_speaker_column_visibility()
        self.viewport().update()
        self.speakers_changed.emit(speakers)

    def _update_speaker_column_visibility(self):
        """Only show the speaker column when there are speakers to show."""
        if self.has_speakers:
            if not self.isColumnHidden(Column.SPEAKER.value):
                return
            self.showColumn(Column.SPEAKER.value)
            self.setColumnWidth(Column.SPEAKER.value, self.SPEAKER_COLUMN_WIDTH)
        elif not self.isColumnHidden(Column.SPEAKER.value):
            self.hideColumn(Column.SPEAKER.value)
        else:
            return

        # Give the text columns back the space the speaker column used
        if self.parent() is not None:
            self.resizeEvent(None)

    def selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.selectionModel().selectedRows()})

    def assign_speaker_to_rows(self, rows: list[int], speaker: str):
        speaker = speaker.strip()
        model = self.model()
        self._bulk_updating_speakers = True
        try:
            for row in sorted(set(rows)):
                if 0 <= row < model.rowCount():
                    model.setData(model.index(row, Column.SPEAKER.value), speaker)
            model.submitAll()
        finally:
            self._bulk_updating_speakers = False
        self._refresh_speakers()

    def _show_context_menu(self, position):
        index = self.indexAt(position)
        if index.isValid() and index.row() not in self.selected_rows():
            self.clearSelection()
            self.selectRow(index.row())

        rows = self.selected_rows()
        menu = QMenu(self)
        assign_menu = menu.addMenu(_("Assign Speaker"))
        assign_menu.setEnabled(bool(rows))

        unassigned_action = assign_menu.addAction(_("Unassigned"))
        unassigned_action.triggered.connect(
            lambda: self.assign_speaker_to_rows(rows, "")
        )
        if self.speaker_names():
            assign_menu.addSeparator()
        for speaker in self.speaker_names():
            action = assign_menu.addAction(speaker)
            action.triggered.connect(
                lambda checked=False, name=speaker: self.assign_speaker_to_rows(
                    rows, name
                )
            )
        assign_menu.addSeparator()
        new_speaker_action = assign_menu.addAction(_("New Speaker…"))
        new_speaker_action.triggered.connect(
            lambda: self._assign_new_speaker(rows)
        )

        menu.exec(self.viewport().mapToGlobal(position))

    def _assign_new_speaker(self, rows: list[int]):
        speaker, accepted = QInputDialog.getText(
            self,
            _("New Speaker"),
            _("Speaker name:"),
        )
        if accepted and speaker.strip():
            self.assign_speaker_to_rows(rows, speaker)

    def segments(self) -> list[QSqlRecord]:
        if self._segments_cache is not None:
            return self._segments_cache
        self._fetch_all_rows()
        self._segments_cache = [self.model().record(i) for i in range(self.model().rowCount())]
        return self._segments_cache

    def find_segment_index_at(self, position_ms: int) -> int:
        """Binary search for the segment containing position_ms. Returns -1 if not found."""
        segs = self.segments()
        lo, hi = 0, len(segs) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            start = segs[mid].value("start_time")
            end = segs[mid].value("end_time")
            if start <= position_ms < end:
                return mid
            elif position_ms < start:
                hi = mid - 1
            else:
                lo = mid + 1
        return -1

    def find_segment_row_by_id(self, segment_id) -> int:
        """Linear search for segment row by id. Returns -1 if not found."""
        for i, seg in enumerate(self.segments()):
            if seg.value("id") == segment_id:
                return i
        return -1

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
