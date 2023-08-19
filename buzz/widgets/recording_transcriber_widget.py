import enum
from enum import auto
from typing import Optional, Tuple

from PyQt6.QtCore import QThread, Qt, QThreadPool
from PyQt6.QtGui import QTextCursor, QCloseEvent
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QMessageBox

from buzz.dialogs import show_model_download_error_dialog
from buzz.locale import _
from buzz.model_loader import (
    ModelDownloader,
    TranscriptionModel,
    ModelType,
    WhisperModelSize,
)
from buzz.recording import RecordingAmplitudeListener
from buzz.recording_transcriber import RecordingTranscriber
from buzz.settings.settings import Settings
from buzz.transcriber import (
    TranscriptionOptions,
    LOADED_WHISPER_DLL,
    Task,
    DEFAULT_WHISPER_TEMPERATURE,
)
from buzz.widgets.audio_devices_combo_box import AudioDevicesComboBox
from buzz.widgets.audio_meter_widget import AudioMeterWidget
from buzz.widgets.model_download_progress_dialog import ModelDownloadProgressDialog
from buzz.widgets.record_button import RecordButton
from buzz.widgets.text_display_box import TextDisplayBox
from buzz.widgets.transcriber.transcription_options_group_box import (
    TranscriptionOptionsGroupBox,
)


class RecordingTranscriberWidget(QWidget):
    current_status: "RecordingStatus"
    transcription_options: TranscriptionOptions
    selected_device_id: Optional[int]
    model_download_progress_dialog: Optional[ModelDownloadProgressDialog] = None
    transcriber: Optional[RecordingTranscriber] = None
    model_loader: Optional[ModelDownloader] = None
    transcription_thread: Optional[QThread] = None
    recording_amplitude_listener: Optional[RecordingAmplitudeListener] = None
    device_sample_rate: Optional[int] = None

    class RecordingStatus(enum.Enum):
        STOPPED = auto()
        RECORDING = auto()

    def __init__(
        self, parent: Optional[QWidget] = None, flags: Optional[Qt.WindowType] = None
    ) -> None:
        super().__init__(parent)

        if flags is not None:
            self.setWindowFlags(flags)

        layout = QVBoxLayout(self)

        self.current_status = self.RecordingStatus.STOPPED
        self.setWindowTitle(_("Live Recording"))

        self.settings = Settings()
        default_language = self.settings.value(
            key=Settings.Key.RECORDING_TRANSCRIBER_LANGUAGE, default_value=""
        )
        self.transcription_options = TranscriptionOptions(
            model=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_MODEL,
                default_value=TranscriptionModel(
                    model_type=ModelType.WHISPER_CPP
                    if LOADED_WHISPER_DLL
                    else ModelType.WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
            ),
            task=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_TASK,
                default_value=Task.TRANSCRIBE,
            ),
            language=default_language if default_language != "" else None,
            initial_prompt=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_INITIAL_PROMPT, default_value=""
            ),
            temperature=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_TEMPERATURE,
                default_value=DEFAULT_WHISPER_TEMPERATURE,
            ),
            word_level_timings=False,
        )

        self.audio_devices_combo_box = AudioDevicesComboBox(self)
        self.audio_devices_combo_box.device_changed.connect(self.on_device_changed)
        self.selected_device_id = self.audio_devices_combo_box.get_default_device_id()

        self.record_button = RecordButton(self)
        self.record_button.clicked.connect(self.on_record_button_clicked)

        self.text_box = TextDisplayBox(self)
        self.text_box.setPlaceholderText(_("Click Record to begin..."))

        transcription_options_group_box = TranscriptionOptionsGroupBox(
            default_transcription_options=self.transcription_options,
            # Live transcription with OpenAI Whisper API not implemented
            model_types=[
                model_type
                for model_type in ModelType
                if model_type is not ModelType.OPEN_AI_WHISPER_API
            ],
            parent=self,
        )
        transcription_options_group_box.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        recording_options_layout = QFormLayout()
        recording_options_layout.addRow(_("Microphone:"), self.audio_devices_combo_box)

        self.audio_meter_widget = AudioMeterWidget(self)

        record_button_layout = QHBoxLayout()
        record_button_layout.addWidget(self.audio_meter_widget)
        record_button_layout.addWidget(self.record_button)

        layout.addWidget(transcription_options_group_box)
        layout.addLayout(recording_options_layout)
        layout.addLayout(record_button_layout)
        layout.addWidget(self.text_box)

        self.setLayout(layout)
        self.setFixedSize(self.sizeHint())

        self.reset_recording_amplitude_listener()

    def on_transcription_options_changed(
        self, transcription_options: TranscriptionOptions
    ):
        self.transcription_options = transcription_options

    def on_device_changed(self, device_id: int):
        self.selected_device_id = device_id
        self.reset_recording_amplitude_listener()

    def reset_recording_amplitude_listener(self):
        if self.recording_amplitude_listener is not None:
            self.recording_amplitude_listener.stop_recording()

        # Listening to audio will fail if there are no input devices
        if self.selected_device_id is None or self.selected_device_id == -1:
            return

        # Get the device sample rate before starting the listener as the PortAudio function
        # fails if you try to get the device's settings while recording is in progress.
        self.device_sample_rate = RecordingTranscriber.get_device_sample_rate(
            self.selected_device_id
        )

        self.recording_amplitude_listener = RecordingAmplitudeListener(
            input_device_index=self.selected_device_id, parent=self
        )
        self.recording_amplitude_listener.amplitude_changed.connect(
            self.on_recording_amplitude_changed
        )
        self.recording_amplitude_listener.start_recording()

    def on_record_button_clicked(self):
        if self.current_status == self.RecordingStatus.STOPPED:
            self.start_recording()
            self.current_status = self.RecordingStatus.RECORDING
            self.record_button.set_recording()
        else:  # RecordingStatus.RECORDING
            self.stop_recording()
            self.set_recording_status_stopped()

    def start_recording(self):
        self.record_button.setDisabled(True)

        model_path = self.transcription_options.model.get_local_model_path()
        if model_path is not None:
            self.on_model_loaded(model_path)
            return

        self.model_loader = ModelDownloader(model=self.transcription_options.model)
        self.model_loader.signals.progress.connect(self.on_download_model_progress)
        self.model_loader.signals.error.connect(self.on_download_model_error)
        self.model_loader.signals.finished.connect(self.on_model_loaded)
        QThreadPool().globalInstance().start(self.model_loader)

    def on_model_loaded(self, model_path: str):
        self.reset_recording_controls()
        self.model_loader = None

        self.transcription_thread = QThread()

        # TODO: make runnable
        self.transcriber = RecordingTranscriber(
            input_device_index=self.selected_device_id,
            sample_rate=self.device_sample_rate,
            transcription_options=self.transcription_options,
            model_path=model_path,
        )

        self.transcriber.moveToThread(self.transcription_thread)

        self.transcription_thread.started.connect(self.transcriber.start)
        self.transcription_thread.finished.connect(
            self.transcription_thread.deleteLater
        )

        self.transcriber.transcription.connect(self.on_next_transcription)

        self.transcriber.finished.connect(self.on_transcriber_finished)
        self.transcriber.finished.connect(self.transcription_thread.quit)
        self.transcriber.finished.connect(self.transcriber.deleteLater)

        self.transcriber.error.connect(self.on_transcriber_error)
        self.transcriber.error.connect(self.transcription_thread.quit)
        self.transcriber.error.connect(self.transcriber.deleteLater)

        self.transcription_thread.start()

    def on_download_model_progress(self, progress: Tuple[float, float]):
        (current_size, total_size) = progress

        if self.model_download_progress_dialog is None:
            self.model_download_progress_dialog = ModelDownloadProgressDialog(
                model_type=self.transcription_options.model.model_type, parent=self
            )
            self.model_download_progress_dialog.canceled.connect(
                self.on_cancel_model_progress_dialog
            )

        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.set_value(
                fraction_completed=current_size / total_size
            )

    def set_recording_status_stopped(self):
        self.record_button.set_stopped()
        self.current_status = self.RecordingStatus.STOPPED

    def on_download_model_error(self, error: str):
        self.reset_model_download()
        show_model_download_error_dialog(self, error)
        self.stop_recording()
        self.set_recording_status_stopped()
        self.record_button.setDisabled(False)

    def on_next_transcription(self, text: str):
        text = text.strip()
        if len(text) > 0:
            self.text_box.moveCursor(QTextCursor.MoveOperation.End)
            if len(self.text_box.toPlainText()) > 0:
                self.text_box.insertPlainText("\n\n")
            self.text_box.insertPlainText(text)
            self.text_box.moveCursor(QTextCursor.MoveOperation.End)

    def stop_recording(self):
        if self.transcriber is not None:
            self.transcriber.stop_recording()
        # Disable record button until the transcription is actually stopped in the background
        self.record_button.setDisabled(True)

    def on_transcriber_finished(self):
        self.reset_record_button()

    def on_transcriber_error(self, error: str):
        self.reset_record_button()
        self.set_recording_status_stopped()
        QMessageBox.critical(
            self,
            "",
            _("An error occurred while starting a new recording:")
            + error
            + ". "
            + _(
                "Please check your audio devices or check the application logs for more information."
            ),
        )

    def on_cancel_model_progress_dialog(self):
        if self.model_loader is not None:
            self.model_loader.cancel()
        self.reset_model_download()
        self.set_recording_status_stopped()
        self.record_button.setDisabled(False)

    def reset_model_download(self):
        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.close()
            self.model_download_progress_dialog = None

    def reset_recording_controls(self):
        # Clear text box placeholder because the first chunk takes a while to process
        self.text_box.setPlaceholderText("")
        self.reset_record_button()
        self.reset_model_download()

    def reset_record_button(self):
        self.record_button.setEnabled(True)

    def on_recording_amplitude_changed(self, amplitude: float):
        self.audio_meter_widget.update_amplitude(amplitude)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.model_loader is not None:
            self.model_loader.cancel()

        self.stop_recording()
        if self.recording_amplitude_listener is not None:
            self.recording_amplitude_listener.stop_recording()
            self.recording_amplitude_listener.deleteLater()

        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_LANGUAGE,
            self.transcription_options.language,
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_TASK, self.transcription_options.task
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_TEMPERATURE,
            self.transcription_options.temperature,
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_INITIAL_PROMPT,
            self.transcription_options.initial_prompt,
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_MODEL, self.transcription_options.model
        )

        return super().closeEvent(event)
