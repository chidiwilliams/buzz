import enum
import typing

from PyQt6.QtCore import QSettings

from buzz.constants import APP_NAME


class Settings:
    settings = QSettings(APP_NAME)

    class Key(enum.Enum):
        RECORDING_TRANSCRIBER_TASK = 'recording-transcriber/task'
        RECORDING_TRANSCRIBER_LANGUAGE = 'recording-transcriber/language'
        FILE_TRANSCRIBER_TASK = 'file-transcriber/task'
        FILE_TRANSCRIBER_LANGUAGE = 'file-transcriber/language'
        FILE_TRANSCRIBER_WORD_LEVEL_TIMINGS = 'file-transcriber/word-level-timings'
        FILE_TRANSCRIBER_EXPORT_FORMATS = 'file-transcriber/export-formats'
        FILE_TRANSCRIBER_MODEL_TYPE = 'file-transcriber/model-type'
        FILE_TRANSCRIBER_WHISPER_MODEL_SIZE = 'file-transcriber/whisper-model-size'
        FILE_TRANSCRIBER_TEMPERATURE = 'file-transcriber/temperature'
        FILE_TRANSCRIBER_INITIAL_PROMPT = 'file-transcriber/initial-prompt'

    def set_value(self, key: Key, value: typing.Any) -> None:
        self.settings.setValue(key.value, value)

    def value(self, key: Key, default_value: typing.Any, value_type: typing.Optional[type] = None) -> typing.Any:
        return self.settings.value(key.value, default_value,
                                   value_type if value_type is not None else type(default_value))
