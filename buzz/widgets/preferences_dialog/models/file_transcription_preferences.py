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
    extract_speech: bool
    temperature: Tuple[float, ...]
    initial_prompt: str
    enable_llm_translation: bool
    llm_prompt: str
    llm_model: str
    output_formats: Set["OutputFormat"]

    def save(self, settings: QSettings) -> None:
        settings.setValue("language", self.language)
        settings.setValue("task", self.task)
        settings.setValue("model", self.model)
        settings.setValue("word_level_timings", self.word_level_timings)
        settings.setValue("extract_speech", self.extract_speech)
        settings.setValue("temperature", self.temperature)
        settings.setValue("initial_prompt", self.initial_prompt)
        settings.setValue("enable_llm_translation", self.enable_llm_translation)
        settings.setValue("llm_model", self.llm_model)
        settings.setValue("llm_prompt", self.llm_prompt)
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

        word_level_timings_value = settings.value("word_level_timings", False)
        word_level_timings = False if word_level_timings_value == "false" \
            else bool(word_level_timings_value)

        extract_speech_value = settings.value("extract_speech", False)
        extract_speech = False if extract_speech_value == "false" \
            else bool(extract_speech_value)

        temperature = settings.value("temperature", DEFAULT_WHISPER_TEMPERATURE)
        initial_prompt = settings.value("initial_prompt", "")
        enable_llm_translation_value = settings.value("enable_llm_translation", False)
        enable_llm_translation = False if enable_llm_translation_value == "false" \
            else bool(enable_llm_translation_value)
        llm_model = settings.value("llm_model", "")
        llm_prompt = settings.value("llm_prompt", "")
        output_formats = settings.value("output_formats", []) or []
        return FileTranscriptionPreferences(
            language=language,
            task=task,
            model=model
            if model.model_type.is_available()
            else TranscriptionModel.default(),
            word_level_timings=word_level_timings,
            extract_speech=extract_speech,
            temperature=temperature,
            initial_prompt=initial_prompt,
            enable_llm_translation=enable_llm_translation,
            llm_model=llm_model,
            llm_prompt=llm_prompt,
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
            enable_llm_translation=transcription_options.enable_llm_translation,
            llm_model=transcription_options.llm_model,
            llm_prompt=transcription_options.llm_prompt,
            word_level_timings=transcription_options.word_level_timings,
            extract_speech=transcription_options.extract_speech,
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
                enable_llm_translation=self.enable_llm_translation,
                llm_model=self.llm_model,
                llm_prompt=self.llm_prompt,
                word_level_timings=self.word_level_timings,
                extract_speech=self.extract_speech,
                model=self.model,
                openai_access_token=openai_access_token,
            ),
            FileTranscriptionOptions(
                output_formats=self.output_formats,
                file_paths=file_paths,
                url=url,
            ),
        )
