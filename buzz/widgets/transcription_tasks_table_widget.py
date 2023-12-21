import enum
import os
from dataclasses import dataclass
from enum import auto
from typing import Optional, Callable

from PyQt6 import QtGui
from PyQt6.QtCore import pyqtSignal, Qt, QModelIndex
from PyQt6.QtWidgets import (
    QTableWidget,
    QWidget,
    QAbstractItemView,
    QTableWidgetItem,
    QMenu,
)

from buzz.locale import _
from buzz.settings.settings import Settings
from buzz.transcriber import FileTranscriptionTask, humanize_language


@dataclass
class TableColDef:
    id: str
    header: str
    column_index: int
    value_getter: Callable[..., str]
    width: Optional[int] = None
    hidden: bool = False
    hidden_toggleable: bool = True


class TranscriptionTasksTableWidget(QTableWidget):
    class Column(enum.Enum):
        TASK_ID = 0
        FILE_NAME = auto()
        MODEL = auto()
        TASK = auto()
        STATUS = auto()

    return_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setRowCount(0)
        self.setAlternatingRowColors(True)
        self.settings = Settings()

        self.column_definitions = [
            TableColDef(
                id="id",
                header=_("ID"),
                column_index=self.Column.TASK_ID.value,
                value_getter=lambda task: str(task.id),
                width=0,
                hidden=True,
                hidden_toggleable=False,
            ),
            TableColDef(
                id="file_name",
                header=_("File Name"),
                column_index=self.Column.FILE_NAME.value,
                value_getter=lambda task: os.path.basename(task.file_path),
                width=250,
                hidden_toggleable=False,
            ),
            TableColDef(
                id="model",
                header=_("Model"),
                column_index=self.Column.MODEL.value,
                value_getter=lambda task: str(task.transcription_options.model),
                width=180,
                hidden=True,
            ),
            TableColDef(
                id="task",
                header=_("Task"),
                column_index=self.Column.TASK.value,
                value_getter=lambda task: self.get_task_label(task),
                width=180,
                hidden=True,
            ),
            TableColDef(
                id="status",
                header=_("Status"),
                column_index=self.Column.STATUS.value,
                value_getter=lambda task: task.status_text(),
                width=180,
                hidden_toggleable=False,
            ),
        ]

        self.setColumnCount(len(self.column_definitions))
        self.verticalHeader().hide()
        self.setHorizontalHeaderLabels(
            [definition.header for definition in self.column_definitions]
        )
        for definition in self.column_definitions:
            if definition.width is not None:
                self.setColumnWidth(definition.column_index, definition.width)
        self.load_column_visibility()

        self.horizontalHeader().setMinimumSectionSize(180)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for definition in self.column_definitions:
            if not definition.hidden_toggleable:
                continue
            action = menu.addAction(definition.header)
            action.setCheckable(True)
            action.setChecked(not self.isColumnHidden(definition.column_index))
            action.toggled.connect(
                lambda checked,
                column_index=definition.column_index: self.on_column_checked(
                    column_index, checked
                )
            )
        menu.exec(event.globalPos())

    def on_column_checked(self, column_index: int, checked: bool):
        self.setColumnHidden(column_index, not checked)
        self.save_column_visibility()

    def save_column_visibility(self):
        self.settings.begin_group(
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY
        )
        for definition in self.column_definitions:
            self.settings.settings.setValue(
                definition.id, not self.isColumnHidden(definition.column_index)
            )
        self.settings.end_group()

    def load_column_visibility(self):
        self.settings.begin_group(
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY
        )
        for definition in self.column_definitions:
            visible = self.settings.settings.value(definition.id, not definition.hidden)
            self.setColumnHidden(definition.column_index, not visible)
        self.settings.end_group()

    def upsert_task(self, task: FileTranscriptionTask):
        task_row_index = self.task_row_index(task.id)
        if task_row_index is None:
            self.insertRow(self.rowCount())

            row_index = self.rowCount() - 1
            for definition in self.column_definitions:
                item = QTableWidgetItem(definition.value_getter(task))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(row_index, definition.column_index, item)
        else:
            status_widget = self.item(task_row_index, self.Column.STATUS.value)
            status_widget.setText(task.status_text())

    @staticmethod
    def get_task_label(task: FileTranscriptionTask) -> str:
        value = task.transcription_options.task.value.capitalize()
        if task.transcription_options.language is not None:
            value += f" ({humanize_language(task.transcription_options.language)})"
        return value

    def clear_task(self, task_id: int):
        task_row_index = self.task_row_index(task_id)
        if task_row_index is not None:
            self.removeRow(task_row_index)

    def task_row_index(self, task_id: int) -> int | None:
        table_items_matching_task_id = [
            item
            for item in self.findItems(str(task_id), Qt.MatchFlag.MatchExactly)
            if item.column() == self.Column.TASK_ID.value
        ]
        if len(table_items_matching_task_id) == 0:
            return None
        return table_items_matching_task_id[0].row()

    @staticmethod
    def find_task_id(index: QModelIndex):
        sibling_index = index.siblingAtColumn(
            TranscriptionTasksTableWidget.Column.TASK_ID.value
        ).data()
        return int(sibling_index) if sibling_index is not None else None

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Return:
            self.return_clicked.emit()
        super().keyPressEvent(event)
