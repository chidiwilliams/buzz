import enum
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from PyQt6.QtCore import pyqtSignal, Qt, QModelIndex, QItemSelection
from PyQt6.QtSql import QSqlTableModel, QSqlRecord
from PyQt6.QtGui import QFontMetrics, QTextOption
from PyQt6.QtWidgets import (
    QWidget,
    QTableView,
    QStyledItemDelegate,
    QAbstractItemView,
    QTextEdit,
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


class TimeStampDelegate(QStyledItemDelegate):
    def displayText(self, value, locale):
        return to_timestamp(value)


class WordWrapDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QTextEdit(parent)
        editor.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        editor.setAcceptRichText(False)

        return editor

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText())


class TranscriptionSegmentModel(QSqlTableModel):
    def __init__(self, transcription_id: UUID):
        super().__init__()
        self.setTable("transcription_segment")
        self.setEditStrategy(QSqlTableModel.EditStrategy.OnFieldChange)
        self.setFilter(f"transcription_id = '{transcription_id}'")

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        if index.column() in (Column.START.value, Column.END.value):
            flags &= ~Qt.ItemFlag.ItemIsEditable
        return flags


class TranscriptionSegmentsEditorWidget(QTableView):
    PARENT_PADDINGS = 40
    segment_selected = pyqtSignal(QSqlRecord)

    def __init__(
            self,
            transcription_id: UUID,
            translator: Translator,
            parent: Optional[QWidget]
    ):
        super().__init__(parent)

        self.translator = translator
        self.translator.translation.connect(self.update_translation)

        model = TranscriptionSegmentModel(transcription_id=transcription_id)
        self.setModel(model)

        timestamp_delegate = TimeStampDelegate()
        word_wrap_delegate = WordWrapDelegate()

        self.column_definitions: list[ColDef] = [
            ColDef("start", _("Start"), Column.START, delegate=timestamp_delegate),
            ColDef("end", _("End"), Column.END, delegate=timestamp_delegate),
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
        self.selectionModel().selectionChanged.connect(self.on_selection_changed)
        model.select()
        model.rowsInserted.connect(self.init_row_height)

        self.has_translations = self.has_non_empty_translation()

        # Show start before end
        self.horizontalHeader().swapSections(1, 2)

        self.init_row_height()

        self.setColumnWidth(Column.START.value, 95)
        self.setColumnWidth(Column.END.value, 95)

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
