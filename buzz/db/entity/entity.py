from abc import ABC

from PyQt6.QtSql import QSqlRecord


class Entity(ABC):
    @classmethod
    def from_record(cls, record: QSqlRecord):
        entity = cls()
        for i in range(record.count()):
            setattr(entity, record.fieldName(i), record.value(i))
        return entity
