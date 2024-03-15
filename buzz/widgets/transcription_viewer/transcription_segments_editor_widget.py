import enum
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from PyQt6.QtCore import pyqtSignal, Qt, QModelIndex, QItemSelection
from PyQt6.QtSql import QSqlTableModel, QSqlRecord
from PyQt6.QtWidgets import (
    QWidget,
    QTableView,
    QStyledItemDelegate,
    QAbstractItemView,
)

from buzz.locale import _
from buzz.transcriber.file_transcriber import to_timestamp


class Column(enum.Enum):
    ID = 0
    END = enum.auto()
    START = enum.auto()
    TEXT = enum.auto()
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
    segment_selected = pyqtSignal(QSqlRecord)

    def __init__(self, transcription_id: UUID, parent: Optional[QWidget]):
        super().__init__(parent)

        model = TranscriptionSegmentModel(transcription_id=transcription_id)
        self.setModel(model)

        timestamp_delegate = TimeStampDelegate()

        self.column_definitions: list[ColDef] = [
            ColDef("start", _("Start"), Column.START, delegate=timestamp_delegate),
            ColDef("end", _("End"), Column.END, delegate=timestamp_delegate),
            ColDef("text", _("Text"), Column.TEXT),
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

        # Show start before end
        self.horizontalHeader().swapSections(1, 2)
        self.resizeColumnsToContents()

    def on_selection_changed(
        self, selected: QItemSelection, _deselected: QItemSelection
    ):
        if selected.indexes():
            self.segment_selected.emit(self.segment(selected.indexes()[0]))

    def segment(self, index: QModelIndex) -> QSqlRecord:
        return self.model().record(index.row())

    def segments(self) -> list[QSqlRecord]:
        return [self.model().record(i) for i in range(self.model().rowCount())]
