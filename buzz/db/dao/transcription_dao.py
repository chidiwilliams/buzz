import uuid
from datetime import datetime
from uuid import UUID

from PyQt6.QtSql import QSqlDatabase

from buzz.db.dao.dao import DAO
from buzz.db.entity.transcription import Transcription
from buzz.transcriber.transcriber import FileTranscriptionTask


class TranscriptionDAO(DAO[Transcription]):
    entity = Transcription

    def __init__(self, db: QSqlDatabase):
        super().__init__("transcription", db)

    def create_transcription(self, task: FileTranscriptionTask):
        query = self._create_query()
        query.prepare(
            """
            INSERT INTO transcription (
                id,
                export_formats,
                file,
                output_folder,
                language,
                model_type,
                source,
                status,
                task,
                time_queued,
                url,
                whisper_model_size,
                hugging_face_model_id,
                word_level_timings,
                extract_speech
            ) VALUES (
                :id,
                :export_formats,
                :file,
                :output_folder,
                :language,
                :model_type,
                :source,
                :status,
                :task,
                :time_queued,
                :url,
                :whisper_model_size,
                :hugging_face_model_id,
                :word_level_timings,
                :extract_speech
            )
            """
        )
        query.bindValue(":id", str(task.uid))
        query.bindValue(
            ":export_formats",
            ", ".join(
                [
                    output_format.value
                    for output_format in task.file_transcription_options.output_formats
                ]
            ),
        )
        query.bindValue(":file", task.file_path)
        query.bindValue(":output_folder", task.output_directory)
        query.bindValue(":language", task.transcription_options.language)
        query.bindValue(
            ":model_type", task.transcription_options.model.model_type.value
        )
        query.bindValue(":source", task.source.value)
        query.bindValue(":status", FileTranscriptionTask.Status.QUEUED.value)
        query.bindValue(":task", task.transcription_options.task.value)
        query.bindValue(":time_queued", datetime.now().isoformat())
        query.bindValue(":url", task.url)
        query.bindValue(
            ":whisper_model_size",
            task.transcription_options.model.whisper_model_size.value
            if task.transcription_options.model.whisper_model_size
            else None,
        )
        query.bindValue(
            ":hugging_face_model_id",
            task.transcription_options.model.hugging_face_model_id
            if task.transcription_options.model.hugging_face_model_id
            else None,
        )
        query.bindValue(
            ":word_level_timings",
            task.transcription_options.word_level_timings
        )
        query.bindValue(
            ":extract_speech",
            task.transcription_options.extract_speech
        )
        if not query.exec():
            raise Exception(query.lastError().text())

    def copy_transcription(self, id: UUID) -> UUID:
        query = self._create_query()
        query.prepare("SELECT * FROM transcription WHERE id = :id")
        query.bindValue(":id", str(id))
        if not query.exec():
            raise Exception(query.lastError().text())
        if not query.next():
            raise Exception("Transcription not found")

        transcription_data = {field.name: query.value(field.name) for field in
                              self.entity.__dataclass_fields__.values()}

        new_id = uuid.uuid4()
        transcription_data["id"] = str(new_id)
        transcription_data["time_queued"] = datetime.now().isoformat()
        transcription_data["status"] = FileTranscriptionTask.Status.QUEUED.value

        query.prepare(
            """
            INSERT INTO transcription (
                id,
                export_formats,
                file,
                output_folder,
                language,
                model_type,
                source,
                status,
                task,
                time_queued,
                url,
                whisper_model_size,
                hugging_face_model_id,
                word_level_timings,
                extract_speech
            ) VALUES (
                :id,
                :export_formats,
                :file,
                :output_folder,
                :language,
                :model_type,
                :source,
                :status,
                :task,
                :time_queued,
                :url,
                :whisper_model_size,
                :hugging_face_model_id,
                :word_level_timings,
                :extract_speech
            )
            """
        )
        for key, value in transcription_data.items():
            query.bindValue(f":{key}", value)
        if not query.exec():
            raise Exception(query.lastError().text())

        return new_id

    def update_transcription_as_started(self, id: UUID):
        query = self._create_query()
        query.prepare(
            """
            UPDATE transcription
            SET status = :status, time_started = :time_started
            WHERE id = :id
        """
        )

        query.bindValue(":id", str(id))
        query.bindValue(":status", FileTranscriptionTask.Status.IN_PROGRESS.value)
        query.bindValue(":time_started", datetime.now().isoformat())
        if not query.exec():
            raise Exception(query.lastError().text())

    def update_transcription_as_failed(self, id: UUID, error: str):
        query = self._create_query()
        query.prepare(
            """
            UPDATE transcription
            SET status = :status, time_ended = :time_ended, error_message = :error_message
            WHERE id = :id
        """
        )

        query.bindValue(":id", str(id))
        query.bindValue(":status", FileTranscriptionTask.Status.FAILED.value)
        query.bindValue(":time_ended", datetime.now().isoformat())
        query.bindValue(":error_message", error)
        if not query.exec():
            raise Exception(query.lastError().text())

    def update_transcription_as_canceled(self, id: UUID):
        query = self._create_query()
        query.prepare(
            """
            UPDATE transcription
            SET status = :status, time_ended = :time_ended
            WHERE id = :id
        """
        )

        query.bindValue(":id", str(id))
        query.bindValue(":status", FileTranscriptionTask.Status.CANCELED.value)
        query.bindValue(":time_ended", datetime.now().isoformat())
        if not query.exec():
            raise Exception(query.lastError().text())

    def update_transcription_progress(self, id: UUID, progress: float):
        query = self._create_query()
        query.prepare(
            """
            UPDATE transcription
            SET status = :status, progress = :progress
            WHERE id = :id
        """
        )

        query.bindValue(":id", str(id))
        query.bindValue(":status", FileTranscriptionTask.Status.IN_PROGRESS.value)
        query.bindValue(":progress", progress)
        if not query.exec():
            raise Exception(query.lastError().text())

    def update_transcription_as_completed(self, id: UUID):
        query = self._create_query()
        query.prepare(
            """
            UPDATE transcription
            SET status = :status, time_ended = :time_ended
            WHERE id = :id
        """
        )

        query.bindValue(":id", str(id))
        query.bindValue(":status", FileTranscriptionTask.Status.COMPLETED.value)
        query.bindValue(":time_ended", datetime.now().isoformat())
        if not query.exec():
            raise Exception(query.lastError().text())
