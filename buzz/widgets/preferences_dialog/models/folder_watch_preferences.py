from dataclasses import dataclass

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

    def save(self, settings: QSettings):
        settings.setValue("enabled", self.enabled)
        settings.setValue("input_folder", self.input_directory)
        settings.setValue("output_directory", self.output_directory)
        settings.setValue("delete_processed_files", self.delete_processed_files)
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
        settings.beginGroup("file_transcription_options")
        file_transcription_options = FileTranscriptionPreferences.load(settings)
        settings.endGroup()
        return FolderWatchPreferences(
            enabled=enabled,
            input_directory=input_folder,
            output_directory=output_folder,
            file_transcription_options=file_transcription_options,
            delete_processed_files=delete_processed_files,
        )
