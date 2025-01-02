import logging
from typing import Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QFormLayout, QHBoxLayout

from buzz.locale import _
from buzz.model_loader import ModelType
from buzz.transcriber.transcriber import (
    TranscriptionOptions,
    FileTranscriptionOptions,
    OutputFormat,
)
from buzz.widgets.transcriber.transcription_options_group_box import (
    TranscriptionOptionsGroupBox,
)


class FileTranscriptionFormWidget(QWidget):
    openai_access_token_changed = pyqtSignal(str)
    transcription_options_changed = pyqtSignal(tuple)

    def __init__(
        self,
        transcription_options: TranscriptionOptions,
        file_transcription_options: FileTranscriptionOptions,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.transcription_options = transcription_options
        self.file_transcription_options = file_transcription_options

        layout = QVBoxLayout(self)

        transcription_options_group_box = TranscriptionOptionsGroupBox(
            default_transcription_options=self.transcription_options, parent=self
        )
        transcription_options_group_box.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        self.word_level_timings_checkbox = QCheckBox(_("Word-level timings"))
        self.word_level_timings_checkbox.setChecked(
            self.transcription_options.word_level_timings
        )
        self.word_level_timings_checkbox.stateChanged.connect(
            self.on_word_level_timings_changed
        )

        file_transcription_layout = QFormLayout()
        file_transcription_layout.addRow("", self.word_level_timings_checkbox)

        self.extract_speech_checkbox = QCheckBox(_("Extract speech"))
        self.extract_speech_checkbox.setChecked(
            self.transcription_options.extract_speech
        )
        self.extract_speech_checkbox.stateChanged.connect(
            self.on_extract_speech_changed
        )

        file_transcription_layout.addRow("", self.extract_speech_checkbox)

        export_format_layout = QHBoxLayout()
        for output_format in OutputFormat:
            export_format_checkbox = QCheckBox(
                f"{output_format.value.upper()}", parent=self
            )
            export_format_checkbox.setChecked(
                output_format in self.file_transcription_options.output_formats
            )
            export_format_checkbox.stateChanged.connect(
                self.get_on_checkbox_state_changed_callback(output_format)
            )
            export_format_layout.addWidget(export_format_checkbox)

        file_transcription_layout.addRow(_("Export:"), export_format_layout)

        layout.addWidget(transcription_options_group_box)
        layout.addLayout(file_transcription_layout)
        self.setLayout(layout)

        self.reset_word_level_timings()

    def on_transcription_options_changed(
        self, transcription_options: TranscriptionOptions
    ):
        self.transcription_options = transcription_options
        self.reset_word_level_timings()
        self.transcription_options_changed.emit(
            (self.transcription_options, self.file_transcription_options)
        )
        if self.transcription_options.openai_access_token != "":
            self.openai_access_token_changed.emit(
                self.transcription_options.openai_access_token
            )

    def on_word_level_timings_changed(self, value: int):
        self.transcription_options.word_level_timings = (
            value == Qt.CheckState.Checked.value
        )

        self.transcription_options_changed.emit(
            (self.transcription_options, self.file_transcription_options)
        )

    def on_extract_speech_changed(self, value: int):
        self.transcription_options.extract_speech = (
            value == Qt.CheckState.Checked.value
        )

        self.transcription_options_changed.emit(
            (self.transcription_options, self.file_transcription_options)
        )

    def get_on_checkbox_state_changed_callback(self, output_format: OutputFormat):
        def on_checkbox_state_changed(state: int):
            if state == Qt.CheckState.Checked.value:
                self.file_transcription_options.output_formats.add(output_format)
            elif state == Qt.CheckState.Unchecked.value:
                self.file_transcription_options.output_formats.remove(output_format)

            self.transcription_options_changed.emit(
                (self.transcription_options, self.file_transcription_options)
            )

        return on_checkbox_state_changed

    def reset_word_level_timings(self):
        self.word_level_timings_checkbox.setDisabled(
            self.transcription_options.model.model_type
            == ModelType.OPEN_AI_WHISPER_API
        )
