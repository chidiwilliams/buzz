import enum
import typing
import logging
import uuid

from PyQt6.QtCore import QSettings

APP_NAME = "Buzz"


class Settings:
    def __init__(self, application=""):
        self.settings = QSettings(APP_NAME, application)
        self.settings.sync()
        logging.debug(f"Settings filename: {self.settings.fileName()}")

    class Key(enum.Enum):
        RECORDING_TRANSCRIBER_TASK = "recording-transcriber/task"
        RECORDING_TRANSCRIBER_MODEL = "recording-transcriber/model"
        RECORDING_TRANSCRIBER_LANGUAGE = "recording-transcriber/language"
        RECORDING_TRANSCRIBER_TEMPERATURE = "recording-transcriber/temperature"
        RECORDING_TRANSCRIBER_INITIAL_PROMPT = "recording-transcriber/initial-prompt"
        RECORDING_TRANSCRIBER_ENABLE_LLM_TRANSLATION = "recording-transcriber/enable-llm-translation"
        RECORDING_TRANSCRIBER_LLM_MODEL = "recording-transcriber/llm-model"
        RECORDING_TRANSCRIBER_LLM_PROMPT = "recording-transcriber/llm-prompt"
        RECORDING_TRANSCRIBER_EXPORT_ENABLED = "recording-transcriber/export-enabled"
        RECORDING_TRANSCRIBER_EXPORT_FOLDER = "recording-transcriber/export-folder"
        RECORDING_TRANSCRIBER_MODE = "recording-transcriber/mode"

        FILE_TRANSCRIBER_TASK = "file-transcriber/task"
        FILE_TRANSCRIBER_MODEL = "file-transcriber/model"
        FILE_TRANSCRIBER_LANGUAGE = "file-transcriber/language"
        FILE_TRANSCRIBER_TEMPERATURE = "file-transcriber/temperature"
        FILE_TRANSCRIBER_INITIAL_PROMPT = "file-transcriber/initial-prompt"
        FILE_TRANSCRIBER_ENABLE_LLM_TRANSLATION = "file-transcriber/enable-llm-translation"
        FILE_TRANSCRIBER_LLM_MODEL = "file-transcriber/llm-model"
        FILE_TRANSCRIBER_LLM_PROMPT = "file-transcriber/llm-prompt"
        FILE_TRANSCRIBER_WORD_LEVEL_TIMINGS = "file-transcriber/word-level-timings"
        FILE_TRANSCRIBER_EXPORT_FORMATS = "file-transcriber/export-formats"

        DEFAULT_EXPORT_FILE_NAME = "transcriber/default-export-file-name"
        CUSTOM_OPENAI_BASE_URL = "transcriber/custom-openai-base-url"
        CUSTOM_FASTER_WHISPER_ID = "transcriber/custom-faster-whisper-id"
        HUGGINGFACE_MODEL_ID = "transcriber/huggingface-model-id"

        SHORTCUTS = "shortcuts"

        FONT_SIZE = "font-size"

        UI_LOCALE = "ui-locale"

        USER_IDENTIFIER = "user-identifier"

        TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY = (
            "transcription-tasks-table/column-visibility"
        )

        MAIN_WINDOW = "main-window"

    def get_user_identifier(self) -> str:
        user_id = self.value(self.Key.USER_IDENTIFIER, "")
        if not user_id:
            user_id = str(uuid.uuid4())
            self.set_value(self.Key.USER_IDENTIFIER, user_id)
        return user_id

    def set_value(self, key: Key, value: typing.Any) -> None:
        self.settings.setValue(key.value, value)

    def save_custom_model_id(self, model) -> None:
        from buzz.model_loader import ModelType
        match model.model_type:
            case ModelType.FASTER_WHISPER:
                self.set_value(
                    Settings.Key.CUSTOM_FASTER_WHISPER_ID,
                    model.hugging_face_model_id,
                )
            case ModelType.HUGGING_FACE:
                self.set_value(
                    Settings.Key.HUGGINGFACE_MODEL_ID,
                    model.hugging_face_model_id,
                )

    def load_custom_model_id(self, model) -> str:
        from buzz.model_loader import ModelType
        match model.model_type:
            case ModelType.FASTER_WHISPER:
                return self.value(
                    Settings.Key.CUSTOM_FASTER_WHISPER_ID,
                    "",
                )
            case ModelType.HUGGING_FACE:
                return self.value(
                    Settings.Key.HUGGINGFACE_MODEL_ID,
                    "",
                )

        return ""

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

    def begin_group(self, group: Key) -> None:
        self.settings.beginGroup(group.value)

    def end_group(self) -> None:
        self.settings.endGroup()

    def sync(self):
        self.settings.sync()

    def get_default_export_file_template(self) -> str:
        return self.value(
            Settings.Key.DEFAULT_EXPORT_FILE_NAME,
            "{{ input_file_name }} ({{ task }}d on {{ date_time }})",
        )
