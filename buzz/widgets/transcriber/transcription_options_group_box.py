import os
import logging
import platform
from typing import Optional, List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QGroupBox, QWidget, QFormLayout, QComboBox, QLabel, QHBoxLayout

from buzz.locale import _
from buzz.settings.settings import Settings
from buzz.widgets.icon import INFO_ICON_PATH
from buzz.model_loader import ModelType, WhisperModelSize, get_whisper_cpp_file_path
from buzz.transcriber.transcriber import TranscriptionOptions, Task
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
        self.settings = Settings()
        self.transcription_options = default_transcription_options

        self.form_layout = QFormLayout(self)

        self.model_type_combo_box = ModelTypeComboBox(
            model_types=model_types,
            default_model=default_transcription_options.model.model_type,
            parent=self,
        )
        self.model_type_combo_box.changed.connect(self.on_model_type_changed)

        self.advanced_settings_dialog = AdvancedSettingsDialog(
            transcription_options=self.transcription_options, parent=self
        )
        self.advanced_settings_dialog.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        self.whisper_model_size_combo_box = QComboBox(self)
        self.whisper_model_size_combo_box.addItems(
            [size.value.title() for size in WhisperModelSize if size not in {WhisperModelSize.CUSTOM}]
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

        self.hugging_face_search_line_edit = HuggingFaceSearchLineEdit(
            default_value=default_transcription_options.model.hugging_face_model_id
        )
        self.hugging_face_search_line_edit.model_selected.connect(
            self.on_hugging_face_model_changed
        )
        self.hugging_face_search_line_edit.setVisible(False)

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

        self.form_layout.addRow(_("Model:"), self.model_type_combo_box)

        if platform.system() == "Darwin" and platform.machine() == "arm64":
            self.whisper_model_size_layout = QHBoxLayout()
            self.whisper_model_size_layout.setContentsMargins(0, 0, 0, 0)
            self.whisper_model_size_layout.setSpacing(0)

            self.whisper_model_size_layout.addWidget(self.whisper_model_size_combo_box)

            self.load_note_tooltip_icon = QLabel()
            self.load_note_tooltip_icon.setPixmap(QIcon(INFO_ICON_PATH).pixmap(23, 23))
            self.load_note_tooltip_icon.setToolTip(
                _("First time use of a model may take up to several minutest to load."))
            self.whisper_model_size_layout.addWidget(self.load_note_tooltip_icon)

            self.form_layout.addRow("", self.whisper_model_size_layout)
        else:
            self.load_note_tooltip_icon = None
            self.whisper_model_size_layout = None
            self.form_layout.addRow("", self.whisper_model_size_combo_box)

        self.form_layout.addRow("", self.hugging_face_search_line_edit)
        self.form_layout.addRow(_("Api Key:"), self.openai_access_token_edit)
        self.form_layout.addRow(_("Task:"), self.tasks_combo_box)
        self.form_layout.addRow(_("Language:"), self.languages_combo_box)

        self.reset_visible_rows()

        self.form_layout.addRow("", self.advanced_settings_button)

        self.setLayout(self.form_layout)

    def on_openai_access_token_edit_changed(self, access_token: str):
        self.transcription_options.openai_access_token = access_token
        self.transcription_options_changed.emit(self.transcription_options)

    def on_language_changed(self, language: str):
        if language == "":
            language = None

        self.transcription_options.language = language
        self.transcription_options_changed.emit(self.transcription_options)

    def on_task_changed(self, task: Task):
        self.transcription_options.task = task
        self.transcription_options_changed.emit(self.transcription_options)

    def open_advanced_settings(self):
        self.advanced_settings_dialog.exec()

    def on_transcription_options_changed(
        self, transcription_options: TranscriptionOptions
    ):
        self.transcription_options = transcription_options
        self.transcription_options_changed.emit(transcription_options)

    def reset_visible_rows(self):
        model_type = self.transcription_options.model.model_type
        whisper_model_size = self.transcription_options.model.whisper_model_size

        if (model_type == ModelType.HUGGING_FACE
            or (whisper_model_size == WhisperModelSize.CUSTOM
                and model_type == ModelType.FASTER_WHISPER)):
            self.transcription_options.model.hugging_face_model_id = (
                self.settings.load_custom_model_id(self.transcription_options.model))
            self.hugging_face_search_line_edit.setText(
                self.transcription_options.model.hugging_face_model_id)

        self.form_layout.setRowVisible(
            self.hugging_face_search_line_edit,
            (model_type == ModelType.HUGGING_FACE)
            or (model_type == ModelType.FASTER_WHISPER
                and whisper_model_size == WhisperModelSize.CUSTOM),
            )

        # Remove custom model size for whisper
        custom_model_index = (self.whisper_model_size_combo_box
                              .findText(WhisperModelSize.CUSTOM.value.title()))
        if model_type == ModelType.WHISPER and custom_model_index != -1:
            self.whisper_model_size_combo_box.removeItem(custom_model_index)

        # Add custom model size for whisper_cpp
        custom_model_index = (self.whisper_model_size_combo_box
                              .findText(WhisperModelSize.CUSTOM.value.title()))
        if (model_type == ModelType.WHISPER_CPP
                and os.path.isfile(get_whisper_cpp_file_path(size=WhisperModelSize.CUSTOM))
                and custom_model_index == -1):
            self.whisper_model_size_combo_box.addItem(
                WhisperModelSize.CUSTOM.value.title()
            )

        # Add custom model size for faster_whisper
        custom_model_index = (self.whisper_model_size_combo_box
                              .findText(WhisperModelSize.CUSTOM.value.title()))
        if model_type == ModelType.FASTER_WHISPER and custom_model_index == -1:
            self.whisper_model_size_combo_box.addItem(
                WhisperModelSize.CUSTOM.value.title()
            )

        self.whisper_model_size_combo_box.setCurrentText(
            self.transcription_options.model.whisper_model_size.value.title()
        )

        self.form_layout.setRowVisible(
            self.whisper_model_size_combo_box,
            (model_type == ModelType.WHISPER)
            or (model_type == ModelType.WHISPER_CPP)
            or (model_type == ModelType.FASTER_WHISPER),
        )
        if self.whisper_model_size_layout is not None:
            self.form_layout.setRowVisible(
                self.whisper_model_size_layout,
                (model_type == ModelType.WHISPER)
                or (model_type == ModelType.WHISPER_CPP)
                or (model_type == ModelType.FASTER_WHISPER),
            )

        self.form_layout.setRowVisible(
            self.openai_access_token_edit, model_type == ModelType.OPEN_AI_WHISPER_API
        )

        # Note on Apple Silicon Macs
        if self.load_note_tooltip_icon is not None:
            self.load_note_tooltip_icon.setVisible(
                self.transcription_options.model.model_type == ModelType.WHISPER_CPP
            )

    def on_model_type_changed(self, model_type: ModelType):
        self.transcription_options.model.model_type = model_type
        if not model_type.supports_initial_prompt:
            self.transcription_options.initial_prompt = ""

        self.reset_visible_rows()
        self.transcription_options_changed.emit(self.transcription_options)

    def on_whisper_model_size_changed(self, text: str):
        model_size = WhisperModelSize(text.lower())
        self.transcription_options.model.whisper_model_size = model_size

        self.reset_visible_rows()

        self.transcription_options_changed.emit(self.transcription_options)

    def on_hugging_face_model_changed(self, model: str):
        self.transcription_options.model.hugging_face_model_id = model
        self.transcription_options_changed.emit(self.transcription_options)

        self.settings.save_custom_model_id(self.transcription_options.model)
