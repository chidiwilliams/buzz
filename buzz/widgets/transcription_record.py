from uuid import UUID

from PyQt6.QtSql import QSqlRecord

from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task


class TranscriptionRecord:
    @staticmethod
    def id(record: QSqlRecord) -> UUID:
        return UUID(hex=record.value("id"))

    @staticmethod
    def model(record: QSqlRecord) -> TranscriptionModel:
        return TranscriptionModel(
            model_type=ModelType(record.value("model_type")),
            whisper_model_size=WhisperModelSize(record.value("whisper_model_size"))
            if record.value("whisper_model_size")
            else None,
        )

    @staticmethod
    def task(record: QSqlRecord) -> Task:
        return Task(record.value("task"))
