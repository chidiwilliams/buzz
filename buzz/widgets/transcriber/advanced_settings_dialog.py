from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QDialogButtonBox,
    QFormLayout,
    QPlainTextEdit,
)

from buzz.widgets.transcriber.temperature_validator import TemperatureValidator
from buzz.locale import _
from buzz.model_loader import ModelType
from buzz.transcriber import TranscriptionOptions
from buzz.widgets.line_edit import LineEdit


class AdvancedSettingsDialog(QDialog):
    transcription_options: TranscriptionOptions
    transcription_options_changed = pyqtSignal(TranscriptionOptions)

    def __init__(
        self, transcription_options: TranscriptionOptions, parent: QWidget | None = None
    ):
        super().__init__(parent)

        self.transcription_options = transcription_options

        self.setWindowTitle(_("Advanced Settings"))

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton(QDialogButtonBox.StandardButton.Ok), self
        )
        button_box.accepted.connect(self.accept)

        layout = QFormLayout(self)

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

        self.initial_prompt_text_edit = QPlainTextEdit(
            transcription_options.initial_prompt, self
        )
        self.initial_prompt_text_edit.textChanged.connect(
            self.on_initial_prompt_changed
        )
        self.initial_prompt_text_edit.setEnabled(
            transcription_options.model.model_type == ModelType.WHISPER
        )

        layout.addRow(_("Temperature:"), self.temperature_line_edit)
        layout.addRow(_("Initial Prompt:"), self.initial_prompt_text_edit)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.setFixedSize(self.sizeHint())

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
