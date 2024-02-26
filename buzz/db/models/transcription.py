from datetime import datetime
from typing import List
from uuid import UUID

from PyQt6.QtSql import QSqlQuery

from buzz.transcriber.transcriber import FileTranscriptionTask, Segment


def create_transcription(task: FileTranscriptionTask):
    query = QSqlQuery()
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
            whisper_model_size
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
            :whisper_model_size
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
    query.bindValue(":model_type", task.transcription_options.model.model_type.value)
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
    if not query.exec():
        raise Exception(query.lastError().text())


def update_transcription_as_started(id: UUID):
    query = QSqlQuery()
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


def update_transcription_as_failed(id: UUID, error: str):
    query = QSqlQuery()
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


def update_transcription_as_canceled(id: UUID):
    query = QSqlQuery()
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


def update_transcription_progress(id: UUID, progress: float):
    query = QSqlQuery()
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


def update_transcription_as_completed(id: UUID, segments: List[Segment]):
    query = QSqlQuery()
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

    for segment in segments:
        query = QSqlQuery()
        query.prepare(
            """
            INSERT INTO transcription_segment (
                end_time,
                start_time,
                text,
                transcription_id
            ) VALUES (
                :end_time,
                :start_time,
                :text,
                :transcription_id
            )
        """
        )

        query.bindValue(":end_time", segment.end)
        query.bindValue(":start_time", segment.start)
        query.bindValue(":text", segment.text)
        query.bindValue(":transcription_id", str(id))
        if not query.exec():
            raise Exception(query.lastError().text())
