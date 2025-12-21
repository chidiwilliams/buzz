from typing import List
from uuid import UUID

from buzz.db.dao.transcription_dao import TranscriptionDAO
from buzz.db.dao.transcription_segment_dao import TranscriptionSegmentDAO
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.transcriber.transcriber import Segment


class TranscriptionService:
    def __init__(
        self,
        transcription_dao: TranscriptionDAO,
        transcription_segment_dao: TranscriptionSegmentDAO,
    ):
        self.transcription_dao = transcription_dao
        self.transcription_segment_dao = transcription_segment_dao

    def create_transcription(self, task):
        self.transcription_dao.create_transcription(task)

    def copy_transcription(self, id: UUID) -> UUID:
        return self.transcription_dao.copy_transcription(id)

    def update_transcription_as_started(self, id: UUID):
        self.transcription_dao.update_transcription_as_started(id)

    def update_transcription_as_failed(self, id: UUID, error: str):
        self.transcription_dao.update_transcription_as_failed(id, error)

    def update_transcription_as_canceled(self, id: UUID):
        self.transcription_dao.update_transcription_as_canceled(id)

    def update_transcription_progress(self, id: UUID, progress: float):
        self.transcription_dao.update_transcription_progress(id, progress)

    def update_transcription_as_completed(self, id: UUID, segments: List[Segment]):
        self.transcription_dao.update_transcription_as_completed(id)
        for segment in segments:
            self.transcription_segment_dao.insert(
                TranscriptionSegment(
                    start_time=segment.start,
                    end_time=segment.end,
                    text=segment.text,
                    translation='',
                    transcription_id=str(id),
                )
            )

    def update_transcription_file_and_name(self, id: UUID, file_path: str, name: str | None = None):
        self.transcription_dao.update_transcription_file_and_name(id, file_path, name)

    def update_transcription_name(self, id: UUID, name: str):
        self.transcription_dao.update_transcription_name(id, name)

    def update_transcription_notes(self, id: UUID, notes: str):
        self.transcription_dao.update_transcription_notes(id, notes)

    def reset_transcription_for_restart(self, id: UUID):
        self.transcription_dao.reset_transcription_for_restart(id)

    def replace_transcription_segments(self, id: UUID, segments: List[Segment]):
        self.transcription_segment_dao.delete_segments(id)
        for segment in segments:
            self.transcription_segment_dao.insert(
                TranscriptionSegment(
                    start_time=segment.start,
                    end_time=segment.end,
                    text=segment.text,
                    translation='',
                    transcription_id=str(id),
                )
            )

    def get_transcription_segments(self, transcription_id: UUID):
        return self.transcription_segment_dao.get_segments(transcription_id)

    def update_segment_translation(self, segment_id: int, translation: str):
        return self.transcription_segment_dao.update_segment_translation(segment_id, translation)
