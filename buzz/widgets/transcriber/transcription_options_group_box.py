from typing import Optional, List, Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGroupBox, QWidget, QFormLayout, QComboBox

from buzz.locale import _
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber import TranscriptionOptions, Task
from buzz.widgets.model_type_combo_box import ModelTypeComboBox
from buzz.widgets.openai_api_key_line_edit import OpenAIAPIKeyLineEdit
from buzz.widgets.transcriber.advanced_settings_button import AdvancedSettingsButton
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog
from buzz.widgets.transcriber.hugging_face_search_line_edit import (
    HuggingFaceSearchLineEdit,
)
from buzz.widgets.transcriber.languages_combo_box import LanguagesComboBox
from buzz.widgets.transcriber.tasks_combo_box import TasksComboBox


class TranscriptionOptionsGroupBox(QGroupBox):
    transcription_options: TranscriptionOptions
    transcription_options_changed = pyqtSignal(TranscriptionOptions)

    def __init__(
        self,
        default_transcription_options: TranscriptionOptions = TranscriptionOptions(),
        model_types: Optional[List[ModelType]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(title="", parent=parent)
        self.transcription_options = default_transcription_options

        self.form_layout = QFormLayout(self)

        self.tasks_combo_box = TasksComboBox(
            default_task=self.transcription_options.task, parent=self
        )
        self.tasks_combo_box.taskChanged.connect(self.on_task_changed)

        self.languages_combo_box = LanguagesComboBox(
            default_language=self.transcription_options.language, parent=self
        )
        self.languages_combo_box.languageChanged.connect(self.on_language_changed)

        self.advanced_settings_button = AdvancedSettingsButton(self)
        self.advanced_settings_button.clicked.connect(self.open_advanced_settings)

        self.hugging_face_search_line_edit = HuggingFaceSearchLineEdit()
        self.hugging_face_search_line_edit.model_selected.connect(
            self.on_hugging_face_model_changed
        )

        self.model_type_combo_box = ModelTypeComboBox(
            model_types=model_types,
            default_model=default_transcription_options.model.model_type,
            parent=self,
        )
        self.model_type_combo_box.changed.connect(self.on_model_type_changed)

        self.whisper_model_size_combo_box = QComboBox(self)
        self.whisper_model_size_combo_box.addItems(
            [size.value.title() for size in WhisperModelSize]
        )
        if default_transcription_options.model.whisper_model_size is not None:
            self.whisper_model_size_combo_box.setCurrentText(
                default_transcription_options.model.whisper_model_size.value.title()
            )
        self.whisper_model_size_combo_box.currentTextChanged.connect(
            self.on_whisper_model_size_changed
        )

        self.openai_access_token_edit = OpenAIAPIKeyLineEdit(
            key=default_transcription_options.openai_access_token, parent=self
        )
        self.openai_access_token_edit.key_changed.connect(
            self.on_openai_access_token_edit_changed
        )

        self.form_layout.addRow(_("Model:"), self.model_type_combo_box)
        self.form_layout.addRow("", self.whisper_model_size_combo_box)
        self.form_layout.addRow("", self.hugging_face_search_line_edit)
        self.form_layout.addRow("Access Token:", self.openai_access_token_edit)
        self.form_layout.addRow(_("Task:"), self.tasks_combo_box)
        self.form_layout.addRow(_("Language:"), self.languages_combo_box)

        self.reset_visible_rows()

        self.form_layout.addRow("", self.advanced_settings_button)

        self.setLayout(self.form_layout)

    def on_openai_access_token_edit_changed(self, access_token: str):
        self.transcription_options.openai_access_token = access_token
        self.transcription_options_changed.emit(self.transcription_options)

    def on_language_changed(self, language: str):
        self.transcription_options.language = language
        self.transcription_options_changed.emit(self.transcription_options)

    def on_task_changed(self, task: Task):
        self.transcription_options.task = task
        self.transcription_options_changed.emit(self.transcription_options)

    def on_temperature_changed(self, temperature: Tuple[float, ...]):
        self.transcription_options.temperature = temperature
        self.transcription_options_changed.emit(self.transcription_options)

    def on_initial_prompt_changed(self, initial_prompt: str):
        self.transcription_options.initial_prompt = initial_prompt
        self.transcription_options_changed.emit(self.transcription_options)

    def open_advanced_settings(self):
        dialog = AdvancedSettingsDialog(
            transcription_options=self.transcription_options, parent=self
        )
        dialog.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )
        dialog.exec()

    def on_transcription_options_changed(
        self, transcription_options: TranscriptionOptions
    ):
        self.transcription_options = transcription_options
        self.transcription_options_changed.emit(transcription_options)

    def reset_visible_rows(self):
        model_type = self.transcription_options.model.model_type
        self.form_layout.setRowVisible(
            self.hugging_face_search_line_edit, model_type == ModelType.HUGGING_FACE
        )
        self.form_layout.setRowVisible(
            self.whisper_model_size_combo_box,
            (model_type == ModelType.WHISPER)
            or (model_type == ModelType.WHISPER_CPP)
            or (model_type == ModelType.FASTER_WHISPER),
        )
        self.form_layout.setRowVisible(
            self.openai_access_token_edit, model_type == ModelType.OPEN_AI_WHISPER_API
        )

    def on_model_type_changed(self, model_type: ModelType):
        self.transcription_options.model.model_type = model_type
        self.reset_visible_rows()
        self.transcription_options_changed.emit(self.transcription_options)

    def on_whisper_model_size_changed(self, text: str):
        model_size = WhisperModelSize(text.lower())
        self.transcription_options.model.whisper_model_size = model_size
        self.transcription_options_changed.emit(self.transcription_options)

    def on_hugging_face_model_changed(self, model: str):
        self.transcription_options.model.hugging_face_model_id = model
        self.transcription_options_changed.emit(self.transcription_options)
