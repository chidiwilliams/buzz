import enum
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import auto
from typing import Optional, List
from uuid import UUID

from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtCore import pyqtSignal, QModelIndex
from PyQt6.QtSql import QSqlTableModel, QSqlRecord
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QMenu,
    QHeaderView,
    QTableView,
    QAbstractItemView,
    QStyledItemDelegate,
)

from buzz.db.entity.transcription import Transcription
from buzz.locale import _
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import FileTranscriptionTask, Task, TASK_LABEL_TRANSLATIONS
from buzz.widgets.record_delegate import RecordDelegate
from buzz.widgets.transcription_record import TranscriptionRecord


class Column(enum.Enum):
    ID = 0
    ERROR_MESSAGE = auto()
    EXPORT_FORMATS = auto()
    FILE = auto()
    OUTPUT_FOLDER = auto()
    PROGRESS = auto()
    LANGUAGE = auto()
    MODEL_TYPE = auto()
    SOURCE = auto()
    STATUS = auto()
    TASK = auto()
    TIME_ENDED = auto()
    TIME_QUEUED = auto()
    TIME_STARTED = auto()
    URL = auto()
    WHISPER_MODEL_SIZE = auto()


@dataclass
class ColDef:
    id: str
    header: str
    column: Column
    width: Optional[int] = None
    delegate: Optional[QStyledItemDelegate] = None
    hidden_toggleable: bool = True


def format_record_status_text(record: QSqlRecord) -> str:
    status = FileTranscriptionTask.Status(record.value("status"))
    match status:
        case FileTranscriptionTask.Status.IN_PROGRESS:
            in_progress_label = _("In Progress")
            return f'{in_progress_label} ({record.value("progress") :.0%})'
        case FileTranscriptionTask.Status.COMPLETED:
            status = _("Completed")
            started_at = record.value("time_started")
            completed_at = record.value("time_ended")
            if started_at != "" and completed_at != "":
                status += f" ({TranscriptionTasksTableWidget.format_timedelta(datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at))})"
            return status
        case FileTranscriptionTask.Status.FAILED:
            failed_label = _("Failed")
            return f'{failed_label} ({record.value("error_message")})'
        case FileTranscriptionTask.Status.CANCELED:
            return _("Canceled")
        case FileTranscriptionTask.Status.QUEUED:
            return _("Queued")
        case _:
            return ""

column_definitions = [
    ColDef(
        id="file_name",
        header=_("File Name / URL"),
        column=Column.FILE,
        width=400,
        delegate=RecordDelegate(
            text_getter=lambda record: record.value("url")
            if record.value("url") != ""
            else os.path.basename(record.value("file"))
        ),
        hidden_toggleable=False,
    ),
    ColDef(
        id="model",
        header=_("Model"),
        column=Column.MODEL_TYPE,
        width=180,
        delegate=RecordDelegate(
            text_getter=lambda record: str(TranscriptionRecord.model(record))
        ),
    ),
    ColDef(
        id="task",
        header=_("Task"),
        column=Column.SOURCE,
        width=120,
        delegate=RecordDelegate(
            text_getter=lambda record: TASK_LABEL_TRANSLATIONS[Task(record.value("task"))]
        ),
    ),
    ColDef(
        id="status",
        header=_("Status"),
        column=Column.STATUS,
        width=180,
        delegate=RecordDelegate(text_getter=format_record_status_text),
        hidden_toggleable=False,
    ),
    ColDef(
        id="date_added",
        header=_("Date Added"),
        column=Column.TIME_QUEUED,
        width=180,
        delegate=RecordDelegate(
            text_getter=lambda record: datetime.fromisoformat(
                record.value("time_queued")
            ).strftime("%Y-%m-%d %H:%M:%S")
        ),
    ),
    ColDef(
        id="date_completed",
        header=_("Date Completed"),
        column=Column.TIME_ENDED,
        width=180,
        delegate=RecordDelegate(
            text_getter=lambda record: datetime.fromisoformat(
                record.value("time_ended")
            ).strftime("%Y-%m-%d %H:%M:%S")
            if record.value("time_ended") != ""
            else ""
        ),
    ),
]

class TranscriptionTasksTableHeaderView(QHeaderView):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for definition in column_definitions:
            if not definition.hidden_toggleable:
                continue
            action = menu.addAction(definition.header)
            action.setCheckable(True)
            action.setChecked(not self.isSectionHidden(definition.column.value))
            action.toggled.connect(
                lambda checked, column_index=definition.column.value: self.on_column_checked(
                    column_index, checked
                )
            )
        menu.exec(event.globalPos())

    def on_column_checked(self, column_index: int, checked: bool):
        self.setSectionHidden(column_index, not checked)
        self.parent().save_column_visibility()

class TranscriptionTasksTableWidget(QTableView):
    return_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setHorizontalHeader(TranscriptionTasksTableHeaderView(Qt.Orientation.Horizontal, self))

        self._model = QSqlTableModel()
        self._model.setTable("transcription")
        self._model.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)
        self._model.setSort(Column.TIME_QUEUED.value, Qt.SortOrder.DescendingOrder)

        self.setModel(self._model)

        for i in range(self.model().columnCount()):
            self.hideColumn(i)

        self.settings = Settings()

        self.settings.begin_group(
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY
        )
        for definition in column_definitions:
            self.model().setHeaderData(
                definition.column.value,
                Qt.Orientation.Horizontal,
                definition.header,
            )

            visible = True
            if definition.hidden_toggleable:
                visible = self.settings.settings.value(definition.id, "true") in {"true", "True", True}

            self.setColumnHidden(definition.column.value, not visible)
            if definition.width is not None:
                self.setColumnWidth(definition.column.value, definition.width)
            if definition.delegate is not None:
                self.setItemDelegateForColumn(
                    definition.column.value, definition.delegate
                )
        self.settings.end_group()

        self.model().select()
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.verticalHeader().hide()
        self.setAlternatingRowColors(True)

        # Show date added before date completed
        self.horizontalHeader().swapSections(11, 12)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for definition in column_definitions:
            if not definition.hidden_toggleable:
                continue
            action = menu.addAction(definition.header)
            action.setCheckable(True)
            action.setChecked(not self.isColumnHidden(definition.column.value))
            action.toggled.connect(
                lambda checked,
                column_index=definition.column.value: self.on_column_checked(
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
        for definition in column_definitions:
            self.settings.settings.setValue(
                definition.id, not self.isColumnHidden(definition.column.value)
            )
        self.settings.end_group()

    def copy_selected_fields(self):
        selected_text = ""
        for row in self.selectionModel().selectedRows():
            row_index = row.row()
            file_name = self.model().data(self.model().index(row_index, 3))
            url = self.model().data(self.model().index(row_index, 14))

            selected_text += f"{file_name}{url}\n"

        selected_text = selected_text.rstrip("\n")
        QApplication.clipboard().setText(selected_text)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Return:
            self.return_clicked.emit()

        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selected_fields()
            return

        super().keyPressEvent(event)

    def selected_transcriptions(self) -> List[Transcription]:
        selected = self.selectionModel().selectedRows()
        return [self.transcription(row) for row in selected]

    def delete_transcriptions(self, rows: List[QModelIndex]):
        for row in rows:
            self.model().removeRow(row.row())
        self.model().submitAll()

    def transcription(self, index: QModelIndex) -> Transcription:
        return Transcription.from_record(self.model().record(index.row()))

    def refresh_all(self):
        self.model().select()

    def refresh_row(self, id: UUID):
        for i in range(self.model().rowCount()):
            record = self.model().record(i)
            if record.value("id") == str(id):
                self.model().selectRow(i)
                return

    @staticmethod
    def format_timedelta(delta: timedelta):
        mm, ss = divmod(delta.seconds, 60)
        result = f"{ss}s"
        if mm == 0:
            return result
        hh, mm = divmod(mm, 60)
        result = f"{mm}m {result}"
        if hh == 0:
            return result
        return f"{hh}h {result}"
