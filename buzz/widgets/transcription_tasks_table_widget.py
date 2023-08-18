import datetime
import enum
import os
from enum import auto
from typing import Optional

from PyQt6 import QtGui
from PyQt6.QtCore import pyqtSignal, Qt, QModelIndex
from PyQt6.QtWidgets import QTableWidget, QWidget, QAbstractItemView, QTableWidgetItem

from buzz.locale import _
from buzz.transcriber import FileTranscriptionTask


class TranscriptionTasksTableWidget(QTableWidget):
    class Column(enum.Enum):
        TASK_ID = 0
        FILE_NAME = auto()
        STATUS = auto()

    return_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setRowCount(0)
        self.setAlternatingRowColors(True)

        self.setColumnCount(3)
        self.setColumnHidden(0, True)

        self.verticalHeader().hide()
        self.setHorizontalHeaderLabels([_("ID"), _("File Name"), _("Status")])
        self.setColumnWidth(self.Column.FILE_NAME.value, 250)
        self.setColumnWidth(self.Column.STATUS.value, 180)
        self.horizontalHeader().setMinimumSectionSize(180)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def upsert_task(self, task: FileTranscriptionTask):
        task_row_index = self.task_row_index(task.id)
        if task_row_index is None:
            self.insertRow(self.rowCount())

            row_index = self.rowCount() - 1
            task_id_widget_item = QTableWidgetItem(str(task.id))
            self.setItem(row_index, self.Column.TASK_ID.value, task_id_widget_item)

            file_name_widget_item = QTableWidgetItem(os.path.basename(task.file_path))
            file_name_widget_item.setFlags(
                file_name_widget_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            self.setItem(row_index, self.Column.FILE_NAME.value, file_name_widget_item)

            status_widget_item = QTableWidgetItem(self.get_status_text(task))
            status_widget_item.setFlags(
                status_widget_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            self.setItem(row_index, self.Column.STATUS.value, status_widget_item)
        else:
            status_widget = self.item(task_row_index, self.Column.STATUS.value)
            status_widget.setText(self.get_status_text(task))

    @staticmethod
    def format_timedelta(delta: datetime.timedelta):
        mm, ss = divmod(delta.seconds, 60)
        result = f"{ss}s"
        if mm == 0:
            return result
        hh, mm = divmod(mm, 60)
        result = f"{mm}m {result}"
        if hh == 0:
            return result
        return f"{hh}h {result}"

    @staticmethod
    def get_status_text(task: FileTranscriptionTask):
        if task.status == FileTranscriptionTask.Status.IN_PROGRESS:
            return f'{_("In Progress")} ({task.fraction_completed :.0%})'
        elif task.status == FileTranscriptionTask.Status.COMPLETED:
            status = _("Completed")
            if task.started_at is not None and task.completed_at is not None:
                status += f" ({TranscriptionTasksTableWidget.format_timedelta(task.completed_at - task.started_at)})"
            return status
        elif task.status == FileTranscriptionTask.Status.FAILED:
            return f'{_("Failed")} ({task.error})'
        elif task.status == FileTranscriptionTask.Status.CANCELED:
            return _("Canceled")
        elif task.status == FileTranscriptionTask.Status.QUEUED:
            return _("Queued")

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
