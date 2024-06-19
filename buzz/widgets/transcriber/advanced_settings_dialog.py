from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QDialogButtonBox,
    QCheckBox,
    QPlainTextEdit,
    QFormLayout,
    QLabel,
)

from buzz.locale import _
from buzz.model_loader import ModelType
from buzz.transcriber.transcriber import TranscriptionOptions
from buzz.settings.settings import Settings
from buzz.widgets.line_edit import LineEdit
from buzz.widgets.transcriber.initial_prompt_text_edit import InitialPromptTextEdit
from buzz.widgets.transcriber.temperature_validator import TemperatureValidator


class AdvancedSettingsDialog(QDialog):
    transcription_options: TranscriptionOptions
    transcription_options_changed = pyqtSignal(TranscriptionOptions)

    def __init__(
        self, transcription_options: TranscriptionOptions, parent: QWidget | None = None
    ):
        super().__init__(parent)

        self.transcription_options = transcription_options
        self.settings = Settings()

        self.setWindowTitle(_("Advanced Settings"))

        layout = QFormLayout(self)

        transcription_settings_title= _("Speech recognition settings")
        transcription_settings_title_label = QLabel(f"<h4>{transcription_settings_title}</h4>", self)
        layout.addRow("", transcription_settings_title_label)

        default_temperature_text = ", ".join(
            [str(temp) for temp in transcription_options.temperature]
        )
        self.temperature_line_edit = LineEdit(default_temperature_text, self)
        self.temperature_line_edit.setPlaceholderText(
            _('Comma-separated, e.g. "0.0, 0.2, 0.4, 0.6, 0.8, 1.0"')
        )
        self.temperature_line_edit.setMinimumWidth(170)
        self.temperature_line_edit.textChanged.connect(self.on_temperature_changed)
        self.temperature_line_edit.setValidator(TemperatureValidator(self))
        self.temperature_line_edit.setEnabled(
            transcription_options.model.model_type == ModelType.WHISPER
        )

        layout.addRow(_("Temperature:"), self.temperature_line_edit)

        self.initial_prompt_text_edit = InitialPromptTextEdit(
            transcription_options.initial_prompt,
            transcription_options.model.model_type,
            self,
        )
        self.initial_prompt_text_edit.textChanged.connect(
            self.on_initial_prompt_changed
        )

        layout.addRow(_("Initial Prompt:"), self.initial_prompt_text_edit)

        translation_settings_title= _("Translation settings")
        translation_settings_title_label = QLabel(f"<h4>{translation_settings_title}</h4>", self)
        layout.addRow("", translation_settings_title_label)

        self.enable_llm_translation_checkbox = QCheckBox(_("Enable AI translation"))
        self.enable_llm_translation_checkbox.setChecked(self.transcription_options.enable_llm_translation)
        self.enable_llm_translation_checkbox.stateChanged.connect(self.on_enable_llm_translation_changed)
        layout.addRow("", self.enable_llm_translation_checkbox)

        self.llm_model_line_edit = LineEdit(self.transcription_options.llm_model, self)
        self.llm_model_line_edit.textChanged.connect(
            self.on_llm_model_changed
        )
        self.llm_model_line_edit.setMinimumWidth(170)
        self.llm_model_line_edit.setEnabled(self.transcription_options.enable_llm_translation)
        self.llm_model_line_edit.setPlaceholderText("gpt-3.5-turbo")
        layout.addRow(_("AI model:"), self.llm_model_line_edit)

        self.llm_prompt_text_edit = QPlainTextEdit(self.transcription_options.llm_prompt)
        self.llm_prompt_text_edit.setEnabled(self.transcription_options.enable_llm_translation)
        self.llm_prompt_text_edit.setPlaceholderText(_("Enter instructions for AI on how to translate..."))
        self.llm_prompt_text_edit.setMinimumWidth(170)
        self.llm_prompt_text_edit.setFixedHeight(115)
        self.llm_prompt_text_edit.textChanged.connect(self.on_llm_prompt_changed)
        layout.addRow(_("Instructions for AI:"), self.llm_prompt_text_edit)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton(QDialogButtonBox.StandardButton.Ok), self
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText(_("Ok"))
        button_box.accepted.connect(self.accept)

        layout.addWidget(button_box)

        self.setLayout(layout)
        self.resize(self.sizeHint())

    def on_temperature_changed(self, text: str):
        try:
            temperatures = [float(temp.strip()) for temp in text.split(",")]
            self.transcription_options.temperature = tuple(temperatures)
            self.transcription_options_changed.emit(self.transcription_options)
        except ValueError:
            pass

    def on_initial_prompt_changed(self):
        self.transcription_options.initial_prompt = (
            self.initial_prompt_text_edit.toPlainText()
        )
        self.transcription_options_changed.emit(self.transcription_options)

    def on_enable_llm_translation_changed(self, state):
        self.transcription_options.enable_llm_translation = state == 2
        self.transcription_options_changed.emit(self.transcription_options)

        self.llm_model_line_edit.setEnabled(self.transcription_options.enable_llm_translation)
        self.llm_prompt_text_edit.setEnabled(self.transcription_options.enable_llm_translation)

    def on_llm_model_changed(self, text: str):
        self.transcription_options.llm_model = text
        self.transcription_options_changed.emit(self.transcription_options)

    def on_llm_prompt_changed(self):
        self.transcription_options.llm_prompt = (
            self.llm_prompt_text_edit.toPlainText()
        )
        self.transcription_options_changed.emit(self.transcription_options)
