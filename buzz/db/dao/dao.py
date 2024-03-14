# Adapted from https://github.com/zhiyiYo/Groove
from abc import ABC
from typing import TypeVar, Generic, Any, Type

from PyQt6.QtSql import QSqlDatabase, QSqlQuery, QSqlRecord

from buzz.db.entity.entity import Entity

T = TypeVar("T", bound=Entity)


class DAO(ABC, Generic[T]):
    entity: Type[T]

    def __init__(self, table: str, db: QSqlDatabase):
        self.db = db
        self.table = table

    def insert(self, record: T):
        query = self._create_query()
        keys = record.__dict__.keys()
        query.prepare(
            f"""
            INSERT INTO {self.table} ({", ".join(keys)})
            VALUES ({", ".join([f":{key}" for key in keys])})
        """
        )
        for key, value in record.__dict__.items():
            query.bindValue(f":{key}", value)
        if not query.exec():
            raise Exception(query.lastError().text())

    def find_by_id(self, id: Any) -> T | None:
        query = self._create_query()
        query.prepare(f"SELECT * FROM {self.table} WHERE id = :id")
        query.bindValue(":id", id)
        return self._execute(query)

    def to_entity(self, record: QSqlRecord) -> T:
        entity = self.entity()
        for i in range(record.count()):
            setattr(entity, record.fieldName(i), record.value(i))
        return entity

    def _execute(self, query: QSqlQuery) -> T | None:
        if not query.exec():
            raise Exception(query.lastError().text())
        if not query.first():
            return None
        return self.to_entity(query.record())

    def _create_query(self):
        return QSqlQuery(self.db)
