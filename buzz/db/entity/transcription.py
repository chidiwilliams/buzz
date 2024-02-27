import datetime
import uuid
from dataclasses import dataclass, field

from buzz.db.entity.entity import Entity


@dataclass
class Transcription(Entity):
    status: str
    id: uuid.UUID = field(default_factory=lambda: uuid.uuid4().hex)
    error_message: str | None = None
    time_queued: str = datetime.datetime.now().isoformat()
