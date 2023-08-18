import enum
import typing

from PyQt6.QtCore import QSettings

APP_NAME = "Buzz"


class Settings:
    def __init__(self):
        self.settings = QSettings(APP_NAME)

    class Key(enum.Enum):
        RECORDING_TRANSCRIBER_TASK = "recording-transcriber/task"
        RECORDING_TRANSCRIBER_MODEL = "recording-transcriber/model"
        RECORDING_TRANSCRIBER_LANGUAGE = "recording-transcriber/language"
        RECORDING_TRANSCRIBER_TEMPERATURE = "recording-transcriber/temperature"
        RECORDING_TRANSCRIBER_INITIAL_PROMPT = "recording-transcriber/initial-prompt"

        FILE_TRANSCRIBER_TASK = "file-transcriber/task"
        FILE_TRANSCRIBER_MODEL = "file-transcriber/model"
        FILE_TRANSCRIBER_LANGUAGE = "file-transcriber/language"
        FILE_TRANSCRIBER_TEMPERATURE = "file-transcriber/temperature"
        FILE_TRANSCRIBER_INITIAL_PROMPT = "file-transcriber/initial-prompt"
        FILE_TRANSCRIBER_WORD_LEVEL_TIMINGS = "file-transcriber/word-level-timings"
        FILE_TRANSCRIBER_EXPORT_FORMATS = "file-transcriber/export-formats"

        DEFAULT_EXPORT_FILE_NAME = "transcriber/default-export-file-name"

        SHORTCUTS = "shortcuts"

    def set_value(self, key: Key, value: typing.Any) -> None:
        self.settings.setValue(key.value, value)

    def value(
        self,
        key: Key,
        default_value: typing.Any,
        value_type: typing.Optional[type] = None,
    ) -> typing.Any:
        return self.settings.value(
            key.value,
            default_value,
            value_type if value_type is not None else type(default_value),
        )

    def clear(self):
        self.settings.clear()
