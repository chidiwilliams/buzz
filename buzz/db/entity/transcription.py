import datetime
import os
import uuid
from dataclasses import dataclass, field

from buzz.db.entity.entity import Entity
from buzz.model_loader import ModelType
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import OutputFormat, Task, FileTranscriptionTask


@dataclass
class Transcription(Entity):
    status: str = FileTranscriptionTask.Status.QUEUED.value
    task: str = Task.TRANSCRIBE.value
    model_type: str = ModelType.WHISPER.value
    whisper_model_size: str | None = None
    hugging_face_model_id: str | None = None
    word_level_timings: str | None = None
    extract_speech: str | None = None
    language: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    error_message: str | None = None
    file: str | None = None
    time_queued: str = datetime.datetime.now().isoformat()
    progress: float = 0.0
    time_ended: str | None = None
    time_started: str | None = None
    export_formats: str | None = None
    output_folder: str | None = None
    source: str | None = None
    url: str | None = None

    @property
    def id_as_uuid(self):
        return uuid.UUID(hex=self.id)

    @property
    def status_as_status(self):
        return FileTranscriptionTask.Status(self.status)

    def get_output_file_path(
        self,
        output_format: OutputFormat,
        output_directory: str | None = None,
    ):
        input_file_name = os.path.splitext(os.path.basename(self.file))[0]

        date_time_now = datetime.datetime.now().strftime("%d-%b-%Y %H-%M-%S")

        export_file_name_template = Settings().get_default_export_file_template()

        output_file_name = (
            export_file_name_template.replace("{{ input_file_name }}", input_file_name)
            .replace("{{ task }}", self.task)
            .replace("{{ language }}", self.language or "")
            .replace("{{ model_type }}", self.model_type)
            .replace("{{ model_size }}", self.whisper_model_size or "")
            .replace("{{ date_time }}", date_time_now)
            + f".{output_format.value}"
        )

        output_directory = output_directory or os.path.dirname(self.file)
        return os.path.join(output_directory, output_file_name)
