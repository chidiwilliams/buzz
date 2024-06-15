from dataclasses import dataclass

from buzz.db.entity.entity import Entity


@dataclass
class TranscriptionSegment(Entity):
    start_time: int
    end_time: int
    text: str
    translation: str
    transcription_id: str
    id: int = -1
