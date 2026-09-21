from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QSettings

from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)


@dataclass
class FolderWatchPreferences:
    enabled: bool
    input_directory: str
    output_directory: str
    file_transcription_options: FileTranscriptionPreferences
    delete_processed_files: bool = False
    identify_speakers: bool = False
    speaker_diarizer: str = "msdd"
    speaker_count: Optional[int] = None
    merge_speaker_sentences: bool = True

    def save(self, settings: QSettings):
        settings.setValue("enabled", self.enabled)
        settings.setValue("input_folder", self.input_directory)
        settings.setValue("output_directory", self.output_directory)
        settings.setValue("delete_processed_files", self.delete_processed_files)
        settings.setValue("identify_speakers", self.identify_speakers)
        settings.setValue("speaker_diarizer", self.speaker_diarizer)
        settings.setValue(
            "speaker_count", "" if self.speaker_count is None else self.speaker_count
        )
        settings.setValue("merge_speaker_sentences", self.merge_speaker_sentences)
        settings.beginGroup("file_transcription_options")
        self.file_transcription_options.save(settings)
        settings.endGroup()

    @classmethod
    def load(cls, settings: QSettings) -> "FolderWatchPreferences":
        enabled_value = settings.value("enabled", False)
        enabled = False if enabled_value == "false" else bool(enabled_value)

        input_folder = settings.value("input_folder", defaultValue="", type=str)
        output_folder = settings.value("output_directory", defaultValue="", type=str)
        delete_value = settings.value("delete_processed_files", False)
        delete_processed_files = False if delete_value == "false" else bool(delete_value)

        identify_value = settings.value("identify_speakers", False)
        identify_speakers = False if identify_value == "false" else bool(identify_value)

        speaker_diarizer = settings.value("speaker_diarizer", defaultValue="msdd", type=str)
        if speaker_diarizer not in ("msdd", "sortformer"):
            speaker_diarizer = "msdd"

        speaker_count_value = settings.value("speaker_count", "")
        try:
            speaker_count = int(speaker_count_value)
        except (TypeError, ValueError):
            speaker_count = None

        merge_value = settings.value("merge_speaker_sentences", True)
        merge_speaker_sentences = False if merge_value == "false" else bool(merge_value)

        settings.beginGroup("file_transcription_options")
        file_transcription_options = FileTranscriptionPreferences.load(settings)
        settings.endGroup()
        return FolderWatchPreferences(
            enabled=enabled,
            input_directory=input_folder,
            output_directory=output_folder,
            file_transcription_options=file_transcription_options,
            delete_processed_files=delete_processed_files,
            identify_speakers=identify_speakers,
            speaker_diarizer=speaker_diarizer,
            speaker_count=speaker_count,
            merge_speaker_sentences=merge_speaker_sentences,
        )
