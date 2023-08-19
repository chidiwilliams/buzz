import enum
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QTableWidget, QWidget, QHeaderView, QTableWidgetItem

from buzz.locale import _
from buzz.transcriber import Segment, to_timestamp


class TranscriptionSegmentsEditorWidget(QTableWidget):
    segment_text_changed = pyqtSignal(tuple)
    segment_index_selected = pyqtSignal(int)

    class Column(enum.Enum):
        START = 0
        END = enum.auto()
        TEXT = enum.auto()

    def __init__(self, segments: List[Segment], parent: Optional[QWidget]):
        super().__init__(parent)

        self.segments = segments

        self.setAlternatingRowColors(True)

        self.setColumnCount(3)

        self.verticalHeader().hide()
        self.setHorizontalHeaderLabels([_("Start"), _("End"), _("Text")])
        self.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        for segment in segments:
            row_index = self.rowCount()
            self.insertRow(row_index)

            start_item = QTableWidgetItem(to_timestamp(segment.start))
            start_item.setFlags(
                start_item.flags()
                & ~Qt.ItemFlag.ItemIsEditable
                & ~Qt.ItemFlag.ItemIsSelectable
            )
            self.setItem(row_index, self.Column.START.value, start_item)

            end_item = QTableWidgetItem(to_timestamp(segment.end))
            end_item.setFlags(
                end_item.flags()
                & ~Qt.ItemFlag.ItemIsEditable
                & ~Qt.ItemFlag.ItemIsSelectable
            )
            self.setItem(row_index, self.Column.END.value, end_item)

            text_item = QTableWidgetItem(segment.text)
            self.setItem(row_index, self.Column.TEXT.value, text_item)

        self.itemChanged.connect(self.on_item_changed)
        self.itemSelectionChanged.connect(self.on_item_selection_changed)

    def on_item_changed(self, item: QTableWidgetItem):
        if item.column() == self.Column.TEXT.value:
            self.segment_text_changed.emit((item.row(), item.text()))

    def set_segment_text(self, index: int, text: str):
        self.item(index, self.Column.TEXT.value).setText(text)

    def on_item_selection_changed(self):
        ranges = self.selectedRanges()
        self.segment_index_selected.emit(ranges[0].topRow() if len(ranges) > 0 else -1)
