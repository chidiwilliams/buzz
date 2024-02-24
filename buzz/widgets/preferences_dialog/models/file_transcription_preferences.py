from dataclasses import dataclass
from typing import Optional, Tuple, Set, List

from PyQt6.QtCore import QSettings

from buzz.model_loader import TranscriptionModel
from buzz.transcriber.transcriber import (
    Task,
    OutputFormat,
    DEFAULT_WHISPER_TEMPERATURE,
    TranscriptionOptions,
    FileTranscriptionOptions,
)


@dataclass()
class FileTranscriptionPreferences:
    language: Optional[str]
    task: Task
    model: TranscriptionModel
    word_level_timings: bool
    temperature: Tuple[float, ...]
    initial_prompt: str
    output_formats: Set["OutputFormat"]

    def save(self, settings: QSettings) -> None:
        settings.setValue("language", self.language)
        settings.setValue("task", self.task)
        settings.setValue("model", self.model)
        settings.setValue("word_level_timings", self.word_level_timings)
        settings.setValue("temperature", self.temperature)
        settings.setValue("initial_prompt", self.initial_prompt)
        settings.setValue(
            "output_formats",
            [output_format.value for output_format in self.output_formats],
        )

    @classmethod
    def load(cls, settings: QSettings) -> "FileTranscriptionPreferences":
        language = settings.value("language", None)
        task = settings.value("task", Task.TRANSCRIBE)
        model: TranscriptionModel = settings.value(
            "model", TranscriptionModel.default()
        )
        word_level_timings = bool(settings.value("word_level_timings", False))
        temperature = settings.value("temperature", DEFAULT_WHISPER_TEMPERATURE)
        initial_prompt = settings.value("initial_prompt", "")
        output_formats = settings.value("output_formats", []) or []
        return FileTranscriptionPreferences(
            language=language,
            task=task,
            model=model
            if model.model_type.is_available()
            else TranscriptionModel.default(),
            word_level_timings=word_level_timings,
            temperature=temperature,
            initial_prompt=initial_prompt,
            output_formats=set(
                [OutputFormat(output_format) for output_format in output_formats]
            ),
        )

    @classmethod
    def from_transcription_options(
        cls,
        transcription_options: TranscriptionOptions,
        file_transcription_options: FileTranscriptionOptions,
    ) -> "FileTranscriptionPreferences":
        return FileTranscriptionPreferences(
            task=transcription_options.task,
            language=transcription_options.language,
            temperature=transcription_options.temperature,
            initial_prompt=transcription_options.initial_prompt,
            word_level_timings=transcription_options.word_level_timings,
            model=transcription_options.model,
            output_formats=file_transcription_options.output_formats,
        )

    def to_transcription_options(
        self,
        openai_access_token: Optional[str],
        file_paths: Optional[List[str]] = None,
        url: Optional[str] = None,
    ) -> Tuple[TranscriptionOptions, FileTranscriptionOptions]:
        return (
            TranscriptionOptions(
                task=self.task,
                language=self.language,
                temperature=self.temperature,
                initial_prompt=self.initial_prompt,
                word_level_timings=self.word_level_timings,
                model=self.model,
                openai_access_token=openai_access_token,
            ),
            FileTranscriptionOptions(
                output_formats=self.output_formats,
                file_paths=file_paths,
                url=url,
            ),
        )
