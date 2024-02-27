import datetime
import uuid
from dataclasses import dataclass, field

from buzz.db.entity.entity import Entity


@dataclass
class Transcription(Entity):
    status: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    error_message: str | None = None
    file: str | None = None
    time_queued: str = datetime.datetime.now().isoformat()
