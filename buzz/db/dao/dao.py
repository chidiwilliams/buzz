# Adapted from https://github.com/zhiyiYo/Groove
from abc import ABC
from typing import TypeVar, Generic, Any, Type, List

from PyQt6.QtSql import QSqlDatabase, QSqlQuery, QSqlRecord

from buzz.db.entity.entity import Entity

T = TypeVar("T", bound=Entity)


class DAO(ABC, Generic[T]):
    entity: Type[T]
    ignore_fields = []

    def __init__(self, table: str, db: QSqlDatabase):
        self.db = db
        self.table = table

    def insert(self, record: T):
        query = self._create_query()
        fields = [
            field for field in record.__dict__.keys() if field not in self.ignore_fields
        ]
        query.prepare(
            f"""
            INSERT INTO {self.table} ({", ".join(fields)})
            VALUES ({", ".join([f":{key}" for key in fields])})
        """
        )
        for field in fields:
            query.bindValue(f":{field}", getattr(record, field))

        if not query.exec():
            raise Exception(query.lastError().text())

    def find_by_id(self, id: Any) -> T | None:
        query = self._create_query()
        query.prepare(f"SELECT * FROM {self.table} WHERE id = :id")
        query.bindValue(":id", id)
        return self._execute(query)

    def to_entity(self, record: QSqlRecord) -> T:
        kwargs = {record.fieldName(i): record.value(i) for i in range(record.count())}
        return self.entity(**kwargs)

    def _execute(self, query: QSqlQuery) -> T | None:
        if not query.exec():
            raise Exception(query.lastError().text())
        if not query.first():
            return None
        return self.to_entity(query.record())

    def _execute_all(self, query: QSqlQuery) -> List[T]:
        if not query.exec():
            raise Exception(query.lastError().text())
        entities = []
        while query.next():
            entities.append(self.to_entity(query.record()))
        return entities

    def _create_query(self):
        return QSqlQuery(self.db)
