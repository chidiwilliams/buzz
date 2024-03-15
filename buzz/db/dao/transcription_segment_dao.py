from typing import List
from uuid import UUID

from PyQt6.QtSql import QSqlDatabase

from buzz.db.dao.dao import DAO
from buzz.db.entity.transcription_segment import TranscriptionSegment


class TranscriptionSegmentDAO(DAO[TranscriptionSegment]):
    entity = TranscriptionSegment
    ignore_fields = ["id"]

    def __init__(self, db: QSqlDatabase):
        super().__init__("transcription_segment", db)

    def get_segments(self, transcription_id: UUID) -> List[TranscriptionSegment]:
        query = self._create_query()
        query.prepare(
            f"""
            SELECT * FROM {self.table}
            WHERE transcription_id = :transcription_id
        """
        )
        query.bindValue(":transcription_id", str(transcription_id))
        return self._execute_all(query)
