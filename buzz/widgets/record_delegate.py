from typing import Callable

from PyQt6.QtSql import QSqlRecord, QSqlTableModel
from PyQt6.QtWidgets import QStyledItemDelegate


class RecordDelegate(QStyledItemDelegate):
    def __init__(self, text_getter: Callable[[QSqlRecord], str]):
        super().__init__()
        self.callback = text_getter

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        model: QSqlTableModel = index.model()
        option.text = self.callback(model.record(index.row()))
