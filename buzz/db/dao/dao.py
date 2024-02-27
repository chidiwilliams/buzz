from typing import TypeVar, Generic, Any

from PyQt6.QtSql import QSqlDatabase, QSqlQuery, QSqlRecord

from buzz.db.entity.entity import Entity

T = TypeVar("T", bound=Entity)


class DAO(Generic[T]):
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

    def find_by_id(self, id: Any) -> QSqlRecord | None:
        query = self._create_query()
        query.prepare(f"SELECT * FROM {self.table} WHERE id = :id")
        query.bindValue(":id", id)
        if not query.exec():
            raise Exception(query.lastError().text())
        if not query.first():
            return None
        return query.record()

    def _create_query(self):
        return QSqlQuery(self.db)
