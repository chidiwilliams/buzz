from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QDialogButtonBox,
    QCheckBox,
    QPlainTextEdit,
    QFormLayout,
    QLabel,
    QDoubleSpinBox,
    QLineEdit,
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QFileDialog,
)

from buzz.locale import _
from buzz.model_loader import ModelType
from buzz.transcriber.transcriber import TranscriptionOptions
from buzz.settings.settings import Settings
from buzz.settings.recording_transcriber_mode import RecordingTranscriberMode
from buzz.widgets.line_edit import LineEdit
from buzz.widgets.transcriber.initial_prompt_text_edit import InitialPromptTextEdit
from buzz.widgets.transcriber.temperature_validator import TemperatureValidator


class AdvancedSettingsDialog(QDialog):
    transcription_options: TranscriptionOptions
    transcription_options_changed = pyqtSignal(TranscriptionOptions)

    def __init__(
        self,
        transcription_options: TranscriptionOptions,
        parent: QWidget | None = None,
        show_recording_settings: bool = False,
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
        self.temperature_line_edit.setMinimumWidth(250)
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

        llm_model = self.transcription_options.llm_model or "gpt-4.1-mini"
        self.llm_model_line_edit = LineEdit(llm_model, self)
        self.llm_model_line_edit.textChanged.connect(
            self.on_llm_model_changed
        )
        self.llm_model_line_edit.setMinimumWidth(170)
        self.llm_model_line_edit.setEnabled(self.transcription_options.enable_llm_translation)
        layout.addRow(_("AI model:"), self.llm_model_line_edit)

        default_llm_prompt = self.transcription_options.llm_prompt or _(
            "Please translate each text sent to you from English to Spanish."
        )
        self.llm_prompt_text_edit = QPlainTextEdit(default_llm_prompt)
        self.llm_prompt_text_edit.setEnabled(self.transcription_options.enable_llm_translation)
        self.llm_prompt_text_edit.setMinimumWidth(170)
        self.llm_prompt_text_edit.setFixedHeight(80)
        self.llm_prompt_text_edit.textChanged.connect(self.on_llm_prompt_changed)
        layout.addRow(_("Instructions for AI:"), self.llm_prompt_text_edit)

        if show_recording_settings:
            recording_settings_title = _("Recording settings")
            recording_settings_title_label = QLabel(f"<h4>{recording_settings_title}</h4>", self)
            layout.addRow("", recording_settings_title_label)

            self.silence_threshold_spin_box = QDoubleSpinBox(self)
            self.silence_threshold_spin_box.setRange(0.0, 1.0)
            self.silence_threshold_spin_box.setSingleStep(0.0005)
            self.silence_threshold_spin_box.setDecimals(4)
            self.silence_threshold_spin_box.setValue(transcription_options.silence_threshold)
            self.silence_threshold_spin_box.valueChanged.connect(self.on_silence_threshold_changed)
            layout.addRow(_("Silence threshold:"), self.silence_threshold_spin_box)

            self.line_separator_line_edit = QLineEdit(self)
            line_sep_display = repr(transcription_options.line_separator)[1:-1] or r"\n\n"
            self.line_separator_line_edit.setText(line_sep_display)
            self.line_separator_line_edit.textChanged.connect(self.on_line_separator_changed)
            layout.addRow(_("Line separator:"), self.line_separator_line_edit)

            # Live recording mode
            self.recording_mode_combo = QComboBox(self)
            for mode in RecordingTranscriberMode:
                self.recording_mode_combo.addItem(mode.value)
            self.recording_mode_combo.setCurrentIndex(
                self.settings.value(Settings.Key.RECORDING_TRANSCRIBER_MODE, 0)
            )
            self.recording_mode_combo.currentIndexChanged.connect(self.on_recording_mode_changed)
            layout.addRow(_("Live recording mode:"), self.recording_mode_combo)

            # Export enabled checkbox
            self._export_enabled = self.settings.value(
                Settings.Key.RECORDING_TRANSCRIBER_EXPORT_ENABLED, False
            )
            self.export_enabled_checkbox = QCheckBox(_("Enable live recording export"))
            self.export_enabled_checkbox.setChecked(self._export_enabled)
            self.export_enabled_checkbox.stateChanged.connect(self.on_export_enabled_changed)
            layout.addRow("", self.export_enabled_checkbox)

            # Export folder
            export_folder = self.settings.value(
                Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FOLDER, ""
            )
            self.export_folder_line_edit = LineEdit(export_folder, self)
            self.export_folder_line_edit.setEnabled(self._export_enabled)
            self.export_folder_line_edit.textChanged.connect(self.on_export_folder_changed)
            self.export_folder_browse_button = QPushButton(_("Browse"), self)
            self.export_folder_browse_button.setEnabled(self._export_enabled)
            self.export_folder_browse_button.clicked.connect(self.on_browse_export_folder)
            export_folder_row = QHBoxLayout()
            export_folder_row.addWidget(self.export_folder_line_edit)
            export_folder_row.addWidget(self.export_folder_browse_button)
            layout.addRow(_("Export folder:"), export_folder_row)

            # Export file name template
            export_file_name = self.settings.value(
                Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_NAME, ""
            )
            self.export_file_name_line_edit = LineEdit(export_file_name, self)
            self.export_file_name_line_edit.setEnabled(self._export_enabled)
            self.export_file_name_line_edit.textChanged.connect(self.on_export_file_name_changed)
            layout.addRow(_("Export file name:"), self.export_file_name_line_edit)

            # Export file type
            self.export_file_type_combo = QComboBox(self)
            self.export_file_type_combo.addItem(_("Text file (.txt)"), "txt")
            self.export_file_type_combo.addItem(_("CSV (.csv)"), "csv")
            current_type = self.settings.value(
                Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_TYPE, "txt"
            )
            type_index = self.export_file_type_combo.findData(current_type)
            if type_index >= 0:
                self.export_file_type_combo.setCurrentIndex(type_index)
            self.export_file_type_combo.setEnabled(self._export_enabled)
            self.export_file_type_combo.currentIndexChanged.connect(self.on_export_file_type_changed)
            layout.addRow(_("Export file type:"), self.export_file_type_combo)

            # Max entries
            max_entries = self.settings.value(
                Settings.Key.RECORDING_TRANSCRIBER_EXPORT_MAX_ENTRIES, 0, int
            )
            self.export_max_entries_spin = QSpinBox(self)
            self.export_max_entries_spin.setRange(0, 99)
            self.export_max_entries_spin.setValue(max_entries)
            self.export_max_entries_spin.setEnabled(self._export_enabled)
            self.export_max_entries_spin.valueChanged.connect(self.on_export_max_entries_changed)
            layout.addRow(_("Limit export entries\n(0 = export all):"), self.export_max_entries_spin)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton(QDialogButtonBox.StandardButton.Ok), self
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText(_("Ok"))
        button_box.accepted.connect(self.accept)

        layout.addWidget(button_box)

        self.setLayout(layout)

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

    def on_silence_threshold_changed(self, value: float):
        self.transcription_options.silence_threshold = value
        self.transcription_options_changed.emit(self.transcription_options)

    def on_line_separator_changed(self, text: str):
        try:
            self.transcription_options.line_separator = text.encode().decode("unicode_escape")
        except UnicodeDecodeError:
            return
        self.transcription_options_changed.emit(self.transcription_options)

    def on_recording_mode_changed(self, index: int):
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_MODE, index)

    def on_export_enabled_changed(self, state: int):
        self._export_enabled = state == 2
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_EXPORT_ENABLED, self._export_enabled)
        self.export_folder_line_edit.setEnabled(self._export_enabled)
        self.export_folder_browse_button.setEnabled(self._export_enabled)
        self.export_file_name_line_edit.setEnabled(self._export_enabled)
        self.export_file_type_combo.setEnabled(self._export_enabled)
        self.export_max_entries_spin.setEnabled(self._export_enabled)

    def on_export_folder_changed(self, text: str):
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FOLDER, text)

    def on_browse_export_folder(self):
        folder = QFileDialog.getExistingDirectory(self, _("Select Export Folder"))
        if folder:
            self.export_folder_line_edit.setText(folder)

    def on_export_file_name_changed(self, text: str):
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_NAME, text)

    def on_export_file_type_changed(self, index: int):
        file_type = self.export_file_type_combo.itemData(index)
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_TYPE, file_type)

    def on_export_max_entries_changed(self, value: int):
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_EXPORT_MAX_ENTRIES, value)
