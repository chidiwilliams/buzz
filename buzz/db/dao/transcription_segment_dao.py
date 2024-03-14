from PyQt6.QtSql import QSqlDatabase

from buzz.db.dao.dao import DAO
from buzz.db.entity.transcription_segment import TranscriptionSegment


class TranscriptionSegmentDAO(DAO[TranscriptionSegment]):
    entity = TranscriptionSegment

    def __init__(self, db: QSqlDatabase):
        super().__init__("transcription_segment", db)
