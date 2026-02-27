import csv
import io
import os
import re
import enum
import time
import requests
import logging
import datetime
import sounddevice
from enum import auto
from typing import Optional, Tuple, Any

from PyQt6.QtCore import QThread, Qt, QThreadPool, QTimer
from PyQt6.QtGui import QTextCursor, QCloseEvent, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QHBoxLayout,
    QMessageBox,
    QApplication,
    QPushButton,
    QComboBox,
    QLabel,
    QSpinBox,
    QColorDialog
)

from buzz.dialogs import show_model_download_error_dialog
from buzz.locale import _
from buzz.model_loader import (
    ModelDownloader,
    TranscriptionModel,
    ModelType,
    WhisperModelSize
)
from buzz.store.keyring_store import get_password, Key
from buzz.recording import RecordingAmplitudeListener
from buzz.settings.settings import Settings
from buzz.settings.recording_transcriber_mode import RecordingTranscriberMode
from buzz.transcriber.recording_transcriber import RecordingTranscriber
from buzz.transcriber.transcriber import (
    TranscriptionOptions,
    DEFAULT_WHISPER_TEMPERATURE,
    Task,
)
from buzz.translator import Translator
from buzz.widgets.audio_devices_combo_box import AudioDevicesComboBox
from buzz.widgets.audio_meter_widget import AudioMeterWidget
from buzz.widgets.model_download_progress_dialog import ModelDownloadProgressDialog
from buzz.widgets.record_button import RecordButton
from buzz.widgets.text_display_box import TextDisplayBox
from buzz.widgets.transcriber.transcription_options_group_box import (
    TranscriptionOptionsGroupBox,
)
from buzz.widgets.presentation_window import PresentationWindow
from buzz.widgets.icon import NewWindowIcon, FullscreenIcon, ColorBackgroundIcon, TextColorIcon

REAL_CHARS_REGEX = re.compile(r'\w')
NO_SPACE_BETWEEN_SENTENCES = re.compile(r'([.!?。！？])([A-Z])')


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
        self,
        parent: Optional[QWidget] = None,
        flags: Optional[Qt.WindowType] = None,
        custom_sounddevice: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.sounddevice = custom_sounddevice or sounddevice

        self.upload_url = os.getenv("BUZZ_UPLOAD_URL", "")

        if flags is not None:
            self.setWindowFlags(flags)

        layout = QVBoxLayout(self)

        self.translation_thread = None
        self.translator = None
        self.transcripts = []
        self.translations = []
        self.current_status = self.RecordingStatus.STOPPED
        self.setWindowTitle(_("Live Recording"))

        self.settings = Settings()
        self.transcriber_mode = list(RecordingTranscriberMode)[
            self.settings.value(key=Settings.Key.RECORDING_TRANSCRIBER_MODE, default_value=0)]

        default_language = self.settings.value(
            key=Settings.Key.RECORDING_TRANSCRIBER_LANGUAGE, default_value=""
        )

        model_types = [
            model_type
            for model_type in ModelType
            if model_type.is_available()
        ]
        default_model: Optional[TranscriptionModel] = None
        if len(model_types) > 0:
            default_model = TranscriptionModel(model_type=model_types[0])

        selected_model = self.settings.value(
            key=Settings.Key.RECORDING_TRANSCRIBER_MODEL,
            default_value=default_model,
        )

        if selected_model is None or selected_model.model_type not in model_types:
            selected_model = default_model

        openai_access_token = get_password(key=Key.OPENAI_API_KEY)

        self.transcription_options = TranscriptionOptions(
            model=selected_model,
            task=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_TASK,
                default_value=Task.TRANSCRIBE,
            ),
            language=default_language if default_language != "" else None,
            openai_access_token=openai_access_token,
            initial_prompt=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_INITIAL_PROMPT, default_value=""
            ),
            temperature=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_TEMPERATURE,
                default_value=DEFAULT_WHISPER_TEMPERATURE,
            ),
            word_level_timings=False,
            enable_llm_translation=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_ENABLE_LLM_TRANSLATION,
                default_value=False,
            ),
            llm_model=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_LLM_MODEL, default_value=""
            ),
            llm_prompt=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_LLM_PROMPT, default_value=""
            ),
            silence_threshold=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_SILENCE_THRESHOLD,
                default_value=0.0025,
            ),
            line_separator=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_LINE_SEPARATOR,
                default_value="\n\n",
            ),
        )

        self.audio_devices_combo_box = AudioDevicesComboBox(self)
        self.audio_devices_combo_box.device_changed.connect(self.on_device_changed)
        self.selected_device_id = self.audio_devices_combo_box.get_default_device_id()

        self.record_button = RecordButton(self)
        self.record_button.clicked.connect(self.on_record_button_clicked)
        self.reset_transcriber_controls()

        self.transcription_text_box = TextDisplayBox(self)
        self.transcription_text_box.setPlaceholderText(_("Click Record to begin..."))

        self.translation_text_box = TextDisplayBox(self)
        self.translation_text_box.setPlaceholderText(_("Waiting for AI translation..."))

        self.transcription_options_group_box = TranscriptionOptionsGroupBox(
            default_transcription_options=self.transcription_options,
            model_types=model_types,
            parent=self,
            show_recording_settings=True,
        )
        self.transcription_options_group_box.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        recording_options_layout = QFormLayout()
        recording_options_layout.addRow(_("Microphone:"), self.audio_devices_combo_box)

        self.audio_meter_widget = AudioMeterWidget(self)

        record_button_layout = QHBoxLayout()
        record_button_layout.setContentsMargins(0, 4, 0, 8)
        record_button_layout.addWidget(self.audio_meter_widget, alignment=Qt.AlignmentFlag.AlignVCenter)
        record_button_layout.addWidget(self.record_button)

        layout.addWidget(self.transcription_options_group_box)
        layout.addLayout(recording_options_layout)
        layout.addLayout(record_button_layout)
        layout.addWidget(self.transcription_text_box)
        layout.addWidget(self.translation_text_box)

        if not self.transcription_options.enable_llm_translation:
            self.translation_text_box.hide()

        self.setLayout(layout)
        self.resize(550, 600)

        self.reset_recording_amplitude_listener()

        self._closing = False
        self.transcript_export_file = None
        self.translation_export_file = None
        self.export_enabled = self.settings.value(
            key=Settings.Key.RECORDING_TRANSCRIBER_EXPORT_ENABLED,
            default_value=False,
        )

        #Presentation window
        self.presentation_window: Optional[PresentationWindow] = None

        self.presentation_options_bar = self.create_presentation_options_bar()
        layout.insertWidget(3, self.presentation_options_bar)
        self.presentation_options_bar.hide()
        self.copy_actions_bar = self.create_copy_actions_bar()
        layout.addWidget(self.copy_actions_bar)  # Add at the bottom
        self.copy_actions_bar.hide()

    def create_presentation_options_bar(self) -> QWidget:
        """Crete the presentation options bar widget"""

        bar = QWidget(self)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        self.show_presentation_button = QPushButton(bar)
        self.show_presentation_button.setIcon(NewWindowIcon(bar))
        self.show_presentation_button.setToolTip(_("Show in new window"))
        self.show_presentation_button.clicked.connect(self.on_show_presentation_clicked)
        layout.addWidget(self.show_presentation_button)

        layout.addStretch() #Push other controls to the right

        text_size_label = QLabel(_("Text Size:"), bar)
        layout.addWidget(text_size_label)

        self.text_size_spinbox = QSpinBox(bar)
        self.text_size_spinbox.setRange(10, 100) #10pt to 100pt

        saved_text_size = self.settings.value(
            Settings.Key.PRESENTATION_WINDOW_TEXT_SIZE,
            24,
            int
        )
        self.text_size_spinbox.setValue(saved_text_size)
        self.text_size_spinbox.valueChanged.connect(self.on_text_size_changed)
        layout.addWidget(self.text_size_spinbox)

        #Theme selector
        theme_label = QLabel(_("Theme"), bar)
        layout.addWidget(theme_label)

        self.theme_combo = QComboBox(bar)
        self.theme_combo.addItems([_("Light"), _("Dark"), _("Custom")])
        #Load saved theme
        saved_theme = self.settings.value(
            Settings.Key.PRESENTATION_WINDOW_THEME,
            "light"
        )
        theme_index = {"light": 0, "dark": 1, "custom": 2}.get(saved_theme, 0)
        self.theme_combo.setCurrentIndex(theme_index)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        layout.addWidget(self.theme_combo)

        #Color buttons hidden first, show when custom is selected
        self.text_color_button = QPushButton(bar)
        self.text_color_button.setIcon(TextColorIcon(bar))
        self.text_color_button.setToolTip(_("Text Color"))
        self.text_color_button.clicked.connect(self.on_text_color_clicked)
        self.text_color_button.hide()

        if saved_theme == "custom":
            self.text_color_button.show()
        layout.addWidget(self.text_color_button)

        self.bg_color_button = QPushButton(bar)
        self.bg_color_button.setIcon(ColorBackgroundIcon(bar))
        self.bg_color_button.setToolTip(_("Background Color"))
        self.bg_color_button.clicked.connect(self.on_bg_color_clicked)
        self.bg_color_button.hide()
        if saved_theme == "custom":
            self.bg_color_button.show()
        layout.addWidget(self.bg_color_button)

        self.fullscreen_button = QPushButton(bar)
        self.fullscreen_button.setIcon(FullscreenIcon(bar))
        self.fullscreen_button.setToolTip(_("Fullscreen"))
        self.fullscreen_button.clicked.connect(self.on_fullscreen_clicked)
        self.fullscreen_button.setEnabled(False)
        layout.addWidget(self.fullscreen_button)

        return bar

    def create_copy_actions_bar(self) -> QWidget:
        """Create the copy actions bar widget"""
        bar = QWidget(self)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        layout.addStretch()  # Push button to the right

        self.copy_transcript_button = QPushButton(_("Copy"), bar)
        self.copy_transcript_button.setToolTip(_("Copy transcription to clipboard"))
        self.copy_transcript_button.clicked.connect(self.on_copy_transcript_clicked)
        layout.addWidget(self.copy_transcript_button)

        return bar

    def on_copy_transcript_clicked(self):
        """Handle copy transcript button click"""
        transcript_text = self.transcription_text_box.toPlainText().strip()

        if not transcript_text:
            self.copy_transcript_button.setText(_("Nothing to copy!"))
            QTimer.singleShot(1500, lambda: self.copy_transcript_button.setText(_("Copy")))
            return

        app = QApplication.instance()
        if app is None:
            logging.warning("QApplication instance not available; clipboard disabled")
            self.copy_transcript_button.setText(_("Copy failed"))
            QTimer.singleShot(1500, lambda: self.copy_transcript_button.setText(_("Copy")))
            return

        clipboard = app.clipboard()
        if clipboard is None:
            logging.warning("Clipboard not available")
            self.copy_transcript_button.setText(_("Copy failed"))
            QTimer.singleShot(1500, lambda: self.copy_transcript_button.setText(_("Copy")))
            return

        try:
            clipboard.setText(transcript_text)
        except Exception as e:
            logging.warning("Clipboard error: %s", e)
            self.copy_transcript_button.setText(_("Copy failed"))
            QTimer.singleShot(1500, lambda: self.copy_transcript_button.setText(_("Copy")))
            return

        self.copy_transcript_button.setText(_("Copied!"))
        QTimer.singleShot(2000, lambda: self.copy_transcript_button.setText(_("Copy")))

    def on_show_presentation_clicked(self):
        """Handle click on 'Show in new window' button"""
        if self.presentation_window is None or not self.presentation_window.isVisible():
            #Create new presentation window
            self.presentation_window = PresentationWindow(self)
            self.presentation_window.show()

            #Enable fullscreen button
            self.fullscreen_button.setEnabled(True)

            #Sync current content to presentation window
            transcript_text = self.transcription_text_box.toPlainText()
            if transcript_text:
                self.presentation_window.update_transcripts(transcript_text)

            if self.transcription_options.enable_llm_translation:
                translation_text = self.translation_text_box.toPlainText()
                if translation_text:
                    self.presentation_window.update_translations(translation_text)
        else:
            #Window already open, bring to front
            self.presentation_window.raise_()
            self.presentation_window.activateWindow()

    def on_text_size_changed(self, value: int):
        """Handle text size change"""
        def save_settings():
            self.settings.set_value(Settings.Key.PRESENTATION_WINDOW_TEXT_SIZE, value)
            if self.presentation_window:
                # reload setting to apply new size
                self.presentation_window.load_settings()
        #Incase user drags slider, Debounce by waiting 100ms before saving
        QTimer.singleShot(100, save_settings)

    def on_theme_changed(self, index: int):
        """Handle theme selection change"""
        theme = ["light", "dark", "custom"]
        selected_theme = theme[index]
        self.settings.set_value(Settings.Key.PRESENTATION_WINDOW_THEME, selected_theme)

        #Show/hide color buttons based on selection
        if selected_theme == "custom":
            self.text_color_button.show()
            self.bg_color_button.show()
        else:
            self.text_color_button.hide()
            self.bg_color_button.hide()

        # Apply theme to presentation window
        if self.presentation_window:
            self.presentation_window.load_settings()

    def on_text_color_clicked(self):
        """Handle text color button click"""

        current_color = QColor(
            self.settings.value(
                Settings.Key.PRESENTATION_WINDOW_TEXT_COLOR,
                "#000000"
            )
        )

        color = QColorDialog.getColor(current_color, self, _("Select Text Color"))
        if color.isValid():
            color_hex = color.name()
            self.settings.set_value(Settings.Key.PRESENTATION_WINDOW_TEXT_COLOR, color_hex)
            if self.presentation_window:
                self.presentation_window.load_settings()

    def on_bg_color_clicked(self):
        """Handle background color button click"""

        current_color = QColor(
            self.settings.value(
                Settings.Key.PRESENTATION_WINDOW_BACKGROUND_COLOR,
                "#FFFFFF"
            )
        )

        color = QColorDialog.getColor(current_color, self, _("Select Background Color"))
        if color.isValid():
            color_hex = color.name()
            self.settings.set_value(Settings.Key.PRESENTATION_WINDOW_BACKGROUND_COLOR, color_hex)
            if self.presentation_window:
                self.presentation_window.load_settings()

    def on_fullscreen_clicked(self):
        """Handle fullscreen button click"""
        if self.presentation_window:
            self.presentation_window.toggle_fullscreen()

    def setup_for_export(self):
        export_folder = self.settings.value(
            key=Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FOLDER,
            default_value="",
        )

        date_time_now = datetime.datetime.now().strftime("%d-%b-%Y %H-%M-%S")

        custom_template = self.settings.value(
            key=Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_NAME,
            default_value="",
        )
        export_file_name_template = custom_template if custom_template else Settings().get_default_export_file_template()

        export_file_type = self.settings.value(
            key=Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_TYPE,
            default_value="txt",
        )
        ext = ".csv" if export_file_type == "csv" else ".txt"

        export_file_name = (
                export_file_name_template.replace("{{ input_file_name }}", "live recording")
                .replace("{{ task }}", self.transcription_options.task.value)
                .replace("{{ language }}", self.transcription_options.language or "")
                .replace("{{ model_type }}", self.transcription_options.model.model_type.value)
                .replace("{{ model_size }}", self.transcription_options.model.whisper_model_size or "")
                .replace("{{ date_time }}", date_time_now)
                + ext
        )

        translated_ext = ".translated" + ext

        if not os.path.isdir(export_folder):
            self.export_enabled = False

        self.transcript_export_file = os.path.join(export_folder, export_file_name)
        self.translation_export_file = self.transcript_export_file.replace(ext, translated_ext)

        # Clear export files at the start of each recording session
        for path in (self.transcript_export_file, self.translation_export_file):
            if os.path.isfile(path):
                self.write_to_export_file(path, "", mode="w")

    def on_transcription_options_changed(
        self, transcription_options: TranscriptionOptions
    ):
        self.transcription_options = transcription_options

        if self.transcription_options.enable_llm_translation:
            self.translation_text_box.show()
        else:
            self.translation_text_box.hide()

        self.reset_transcriber_controls()

    def reset_transcriber_controls(self):
        button_enabled = True
        if (self.transcription_options.model.model_type == ModelType.FASTER_WHISPER
                and self.transcription_options.model.whisper_model_size == WhisperModelSize.CUSTOM
                and self.transcription_options.model.hugging_face_model_id == ""):
            button_enabled = False

        if (self.transcription_options.model.model_type == ModelType.HUGGING_FACE
                and self.transcription_options.model.hugging_face_model_id == ""):
            button_enabled = False

        self.record_button.setEnabled(button_enabled)

    def on_device_changed(self, device_id: int):
        self.selected_device_id = device_id
        self.reset_recording_amplitude_listener()

    def reset_recording_amplitude_listener(self):
        if self.recording_amplitude_listener is not None:
            self.recording_amplitude_listener.stop_recording()

        # Listening to audio will fail if there are no input devices
        if self.selected_device_id is None or self.selected_device_id == -1:
            return

        # Get the device sample rate before starting the listener as the PortAudio
        # function # fails if you try to get the device's settings while recording
        # is in progress.
        self.device_sample_rate = RecordingTranscriber.get_device_sample_rate(
            self.selected_device_id
        )
        logging.debug(f"Device sample rate: {self.device_sample_rate}")

        self.recording_amplitude_listener = RecordingAmplitudeListener(
            input_device_index=self.selected_device_id, parent=self
        )
        self.recording_amplitude_listener.amplitude_changed.connect(
            self.on_recording_amplitude_changed, Qt.ConnectionType.QueuedConnection
        )
        self.recording_amplitude_listener.average_amplitude_changed.connect(
            self.audio_meter_widget.update_average_amplitude, Qt.ConnectionType.QueuedConnection
        )
        self.recording_amplitude_listener.start_recording()

    def on_record_button_clicked(self):
        if self.current_status == self.RecordingStatus.STOPPED:
            # Stop amplitude listener and disconnect its signal before resetting
            # to prevent queued amplitude events from overriding the reset
            if self.recording_amplitude_listener is not None:
                self.recording_amplitude_listener.amplitude_changed.disconnect(
                    self.on_recording_amplitude_changed
                )
                self.recording_amplitude_listener.average_amplitude_changed.disconnect(
                    self.audio_meter_widget.update_average_amplitude
                )
                self.recording_amplitude_listener.stop_recording()
                self.recording_amplitude_listener = None
            self.audio_meter_widget.reset_amplitude()
            self.start_recording()
            self.current_status = self.RecordingStatus.RECORDING
            self.record_button.set_recording()
            self.transcription_options_group_box.setEnabled(False)
            self.audio_devices_combo_box.setEnabled(False)
            self.presentation_options_bar.show()
            self.copy_actions_bar.hide()

        else:  # RecordingStatus.RECORDING
            self.stop_recording()
            self.set_recording_status_stopped()
            self.presentation_options_bar.hide()

    def start_recording(self):
        self.record_button.setDisabled(True)
        self.transcripts = []
        self.translations = []

        self.transcription_text_box.clear()
        self.translation_text_box.clear()

        if self.export_enabled:
            self.setup_for_export()

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

        if model_path == "" and self.transcription_options.model.model_type != ModelType.OPEN_AI_WHISPER_API:
            self.on_transcriber_error("")
            logging.error("Model path is empty, cannot start recording.")
            return

        self.transcription_thread = QThread()

        self.transcriber = RecordingTranscriber(
            input_device_index=self.selected_device_id,
            sample_rate=self.device_sample_rate,
            transcription_options=self.transcription_options,
            model_path=model_path,
            sounddevice=self.sounddevice,
        )

        self.transcriber.moveToThread(self.transcription_thread)

        self.transcription_thread.started.connect(self.transcriber.start)
        self.transcription_thread.finished.connect(
            self.transcription_thread.deleteLater
        )

        self.transcriber.transcription.connect(self.on_next_transcription)
        self.transcriber.amplitude_changed.connect(
            self.on_recording_amplitude_changed, Qt.ConnectionType.QueuedConnection
        )
        self.transcriber.average_amplitude_changed.connect(
            self.audio_meter_widget.update_average_amplitude, Qt.ConnectionType.QueuedConnection
        )

        # Stop the separate amplitude listener to avoid two streams on the same device
        if self.recording_amplitude_listener is not None:
            self.recording_amplitude_listener.stop_recording()

        self.transcriber.finished.connect(self.on_transcriber_finished)
        self.transcriber.finished.connect(self.transcription_thread.quit)
        self.transcriber.finished.connect(self.transcriber.deleteLater)

        self.transcriber.error.connect(self.on_transcriber_error)
        self.transcriber.error.connect(self.transcription_thread.quit)
        self.transcriber.error.connect(self.transcriber.deleteLater)

        if self.transcription_options.enable_llm_translation:
            self.translation_thread = QThread()

            self.translator = Translator(
                self.transcription_options,
                self.transcription_options_group_box.advanced_settings_dialog,
            )

            self.translator.moveToThread(self.translation_thread)

            self.translation_thread.started.connect(self.translator.start)
            self.translation_thread.finished.connect(
                self.translation_thread.deleteLater
            )
            self.translation_thread.finished.connect(
                lambda: setattr(self, "translation_thread", None)
            )

            self.translator.finished.connect(self.translation_thread.quit)
            self.translator.finished.connect(self.translator.deleteLater)
            self.translator.finished.connect(
                lambda: setattr(self, "translator", None)
            )

            self.translator.translation.connect(self.on_next_translation)

            self.translation_thread.start()

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

        if self.model_download_progress_dialog is not None and total_size > 0:
            self.model_download_progress_dialog.set_value(
                fraction_completed=current_size / total_size
            )

    def set_recording_status_stopped(self):
        self.record_button.set_stopped()
        self.current_status = self.RecordingStatus.STOPPED
        self.transcription_options_group_box.setEnabled(True)
        self.audio_devices_combo_box.setEnabled(True)
        self.presentation_options_bar.hide()
        self.copy_actions_bar.show() #added this here

    def on_download_model_error(self, error: str):
        self.reset_model_download()
        show_model_download_error_dialog(self, error)
        self.stop_recording()
        self.set_recording_status_stopped()
        self.reset_recording_amplitude_listener()
        self.record_button.setDisabled(False)

    @staticmethod
    def strip_newlines(text):
        return text.replace('\r\n', os.linesep).replace('\n', os.linesep)

    @staticmethod
    def filter_text(text: str):
        text = text.strip()

        if not REAL_CHARS_REGEX.search(text):
            return ""

        return text

    @staticmethod
    def write_to_export_file(file_path: str, content: str, mode: str = "a", retries: int = 5, delay: float = 0.2):
        """Write to an export file with retry logic for Windows file locking."""
        for attempt in range(retries):
            try:
                with open(file_path, mode, encoding='utf-8') as f:
                    f.write(content)
                return
            except PermissionError:
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    logging.warning("Export write failed after %d retries: %s", retries, file_path)
            except OSError as e:
                logging.warning("Export write failed: %s", e)
                return

    @staticmethod
    def write_csv_export(file_path: str, text: str, max_entries: int):
        """Append a new column to a single-row CSV export file, applying max_entries limit."""
        existing_columns = []
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    raw = f.read()
                if raw.strip():
                    reader = csv.reader(io.StringIO(raw))
                    for row in reader:
                        existing_columns = row
                        break
            except OSError:
                pass
        existing_columns.append(text)
        if max_entries > 0:
            existing_columns = existing_columns[-max_entries:]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(existing_columns)
        for attempt in range(5):
            try:
                with open(file_path, "w", encoding='utf-8-sig') as f:
                    f.write(buf.getvalue())
                return
            except PermissionError:
                if attempt < 4:
                    time.sleep(0.2)
                else:
                    logging.warning("CSV export write failed after retries: %s", file_path)
            except OSError as e:
                logging.warning("CSV export write failed: %s", e)
                return

    @staticmethod
    def write_txt_export(file_path: str, text: str, mode: str, max_entries: int, line_separator: str):
        """Write to a TXT export file, applying max_entries limit when needed."""
        if mode == "a":
            RecordingTranscriberWidget.write_to_export_file(file_path, text + line_separator)
            if max_entries > 0 and os.path.isfile(file_path):
                raw = RecordingTranscriberWidget.read_export_file(file_path)
                parts = [p for p in raw.split(line_separator) if p]
                if len(parts) > max_entries:
                    parts = parts[-max_entries:]
                    RecordingTranscriberWidget.write_to_export_file(
                        file_path, line_separator.join(parts) + line_separator, mode="w"
                    )
        elif mode == "prepend":
            existing_content = ""
            if os.path.isfile(file_path):
                existing_content = RecordingTranscriberWidget.read_export_file(file_path)
            new_content = text + line_separator + existing_content
            if max_entries > 0:
                parts = [p for p in new_content.split(line_separator) if p]
                if len(parts) > max_entries:
                    parts = parts[:max_entries]
                new_content = line_separator.join(parts) + line_separator
            RecordingTranscriberWidget.write_to_export_file(file_path, new_content, mode="w")
        else:
            RecordingTranscriberWidget.write_to_export_file(file_path, text, mode=mode)

    @staticmethod
    def read_export_file(file_path: str, retries: int = 5, delay: float = 0.2) -> str:
        """Read an export file with retry logic for Windows file locking."""
        for attempt in range(retries):
            try:
                with open(file_path, "r", encoding='utf-8') as f:
                    return f.read()
            except PermissionError:
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    logging.warning("Export read failed after %d retries: %s", retries, file_path)
            except OSError as e:
                logging.warning("Export read failed: %s", e)
                return ""
        return ""

    # Copilot magic implementation of a sliding window approach to find the longest common substring between two texts,
    # ignoring the initial differences.
    @staticmethod
    def find_common_part(text1: str, text2: str) -> str:
        len1, len2 = len(text1), len(text2)
        max_len = 0
        end_index = 0

        lcsuff = [[0] * (len2 + 1) for _ in range(len1 + 1)]

        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                if text1[i - 1] == text2[j - 1]:
                    lcsuff[i][j] = lcsuff[i - 1][j - 1] + 1
                    if lcsuff[i][j] > max_len:
                        max_len = lcsuff[i][j]
                        end_index = i
                else:
                    lcsuff[i][j] = 0

        common_part = text1[end_index - max_len:end_index]

        return common_part if len(common_part) >= 5 else ""

    @staticmethod
    def merge_text_no_overlap(text1: str, text2: str) -> str:
        overlap_start = 0
        for i in range(1, min(len(text1), len(text2)) + 1):
            if text1[-i:] == text2[:i]:
                overlap_start = i

        return text1 + text2[overlap_start:]

    def process_transcription_merge(self, text: str, texts, text_box, export_file):
        texts.append(text)

        # Remove possibly errorous parts from overlapping audio chunks
        for i in range(len(texts) - 1):
            common_part = self.find_common_part(texts[i], texts[i + 1])
            if common_part:
                common_length = len(common_part)
                texts[i] = texts[i][:texts[i].rfind(common_part) + common_length]
                texts[i + 1] = texts[i + 1][texts[i + 1].find(common_part):]

        merged_texts = ""
        for text in texts:
            merged_texts = self.merge_text_no_overlap(merged_texts, text)

        merged_texts = NO_SPACE_BETWEEN_SENTENCES.sub(r'\1 \2', merged_texts)

        text_box.setPlainText(merged_texts)
        text_box.moveCursor(QTextCursor.MoveOperation.End)

        if self.export_enabled and export_file:
            export_file_type = self.settings.value(
                Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_TYPE, "txt"
            )
            if export_file_type == "csv":
                # For APPEND_AND_CORRECT mode, rewrite the whole CSV with all merged text as a single entry
                self.write_to_export_file(export_file, "", mode="w")
                self.write_csv_export(export_file, merged_texts, 0)
            else:
                self.write_to_export_file(export_file, merged_texts, mode="w")

    def on_next_transcription(self, text: str):
        text = self.filter_text(text)

        if len(text) == 0:
            return

        if self.translator is not None:
            self.translator.enqueue(text)

        export_file_type = self.settings.value(
            Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_TYPE, "txt"
        )
        max_entries = self.settings.value(
            Settings.Key.RECORDING_TRANSCRIBER_EXPORT_MAX_ENTRIES, 0, int
        )

        if self.transcriber_mode == RecordingTranscriberMode.APPEND_BELOW:
            self.transcription_text_box.moveCursor(QTextCursor.MoveOperation.End)
            if len(self.transcription_text_box.toPlainText()) > 0:
                self.transcription_text_box.insertPlainText(self.transcription_options.line_separator)
            self.transcription_text_box.insertPlainText(text)
            self.transcription_text_box.moveCursor(QTextCursor.MoveOperation.End)

            if self.export_enabled and self.transcript_export_file:
                if export_file_type == "csv":
                    self.write_csv_export(self.transcript_export_file, text, max_entries)
                else:
                    self.write_txt_export(self.transcript_export_file, text, "a", max_entries, self.transcription_options.line_separator)

        elif self.transcriber_mode == RecordingTranscriberMode.APPEND_ABOVE:
            self.transcription_text_box.moveCursor(QTextCursor.MoveOperation.Start)
            self.transcription_text_box.insertPlainText(text)
            self.transcription_text_box.insertPlainText(self.transcription_options.line_separator)
            self.transcription_text_box.moveCursor(QTextCursor.MoveOperation.Start)

            if self.export_enabled and self.transcript_export_file:
                if export_file_type == "csv":
                    # For APPEND_ABOVE, prepend in CSV means inserting at beginning of columns
                    existing_columns = []
                    if os.path.isfile(self.transcript_export_file):
                        raw = self.read_export_file(self.transcript_export_file)
                        if raw.strip():
                            reader = csv.reader(io.StringIO(raw))
                            for row in reader:
                                existing_columns = row
                                break
                    new_columns = [text] + existing_columns
                    if max_entries > 0:
                        new_columns = new_columns[:max_entries]
                    buf = io.StringIO()
                    writer = csv.writer(buf)
                    writer.writerow(new_columns)
                    self.write_to_export_file(self.transcript_export_file, buf.getvalue(), mode="w")
                else:
                    self.write_txt_export(self.transcript_export_file, text, "prepend", max_entries, self.transcription_options.line_separator)

        elif self.transcriber_mode == RecordingTranscriberMode.APPEND_AND_CORRECT:
            self.process_transcription_merge(text, self.transcripts, self.transcription_text_box, self.transcript_export_file)

        #Update presentation window if it is open
        if self.presentation_window and self.presentation_window.isVisible():
            #Get current merged text from the translation box
            current_text = self.transcription_text_box.toPlainText()
            self.presentation_window.update_transcripts(current_text)

        # Upload to server
        if self.upload_url:
            try:
                requests.post(
                    url=self.upload_url,
                    json={"kind": "transcript", "text": text},
                    headers={'Content-Type': 'application/json'},
                    timeout=15
                )
            except Exception as e:
                logging.error(f"Transcript upload failed: {str(e)}")

    def on_next_translation(self, text: str, _: Optional[int] = None):
        if len(text) == 0:
            return

        export_file_type = self.settings.value(
            Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FILE_TYPE, "txt"
        )
        max_entries = self.settings.value(
            Settings.Key.RECORDING_TRANSCRIBER_EXPORT_MAX_ENTRIES, 0, int
        )

        if self.transcriber_mode == RecordingTranscriberMode.APPEND_BELOW:
            self.translation_text_box.moveCursor(QTextCursor.MoveOperation.End)
            if len(self.translation_text_box.toPlainText()) > 0:
                self.translation_text_box.insertPlainText(self.transcription_options.line_separator)
            self.translation_text_box.insertPlainText(self.strip_newlines(text))
            self.translation_text_box.moveCursor(QTextCursor.MoveOperation.End)

            if self.export_enabled and self.translation_export_file:
                if export_file_type == "csv":
                    self.write_csv_export(self.translation_export_file, text, max_entries)
                else:
                    self.write_txt_export(self.translation_export_file, text, "a", max_entries, self.transcription_options.line_separator)

        elif self.transcriber_mode == RecordingTranscriberMode.APPEND_ABOVE:
            self.translation_text_box.moveCursor(QTextCursor.MoveOperation.Start)
            self.translation_text_box.insertPlainText(self.strip_newlines(text))
            self.translation_text_box.insertPlainText(self.transcription_options.line_separator)
            self.translation_text_box.moveCursor(QTextCursor.MoveOperation.Start)

            if self.export_enabled and self.translation_export_file:
                if export_file_type == "csv":
                    existing_columns = []
                    if os.path.isfile(self.translation_export_file):
                        raw = self.read_export_file(self.translation_export_file)
                        if raw.strip():
                            reader = csv.reader(io.StringIO(raw))
                            for row in reader:
                                existing_columns = row
                                break
                    new_columns = [text] + existing_columns
                    if max_entries > 0:
                        new_columns = new_columns[:max_entries]
                    buf = io.StringIO()
                    writer = csv.writer(buf)
                    writer.writerow(new_columns)
                    self.write_to_export_file(self.translation_export_file, buf.getvalue(), mode="w")
                else:
                    self.write_txt_export(self.translation_export_file, text, "prepend", max_entries, self.transcription_options.line_separator)

        elif self.transcriber_mode == RecordingTranscriberMode.APPEND_AND_CORRECT:
            self.process_transcription_merge(text, self.translations, self.translation_text_box, self.translation_export_file)

        if self.presentation_window and self.presentation_window.isVisible():
            current_translation = self.translation_text_box.toPlainText()
            self.presentation_window.update_translations(current_translation)

        # Upload to server
        if self.upload_url:
            try:
                requests.post(
                    url=self.upload_url,
                    json={"kind": "translation", "text": text},
                    headers={'Content-Type': 'application/json'},
                    timeout=15
                )
            except Exception as e:
                logging.error(f"Translation upload failed: {str(e)}")

    def stop_recording(self):
        if self.transcriber is not None:
            self.transcriber.stop_recording()

        if self.translator is not None:
            self.translator.stop()

        # Disable record button until the transcription is actually stopped in the background
        self.record_button.setDisabled(True)

    def on_transcriber_finished(self):
        self.reset_record_button()
        # Restart amplitude listener now that the transcription stream is closed
        self.reset_recording_amplitude_listener()

    def on_transcriber_error(self, error: str):
        self.reset_record_button()
        self.set_recording_status_stopped()
        self.reset_recording_amplitude_listener()
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
        self.reset_recording_amplitude_listener()
        self.record_button.setDisabled(False)

    def reset_model_download(self):
        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.canceled.disconnect(
                self.on_cancel_model_progress_dialog
            )
            self.model_download_progress_dialog.close()
            self.model_download_progress_dialog = None

    def reset_recording_controls(self):
        # Clear text box placeholder because the first chunk takes a while to process
        self.transcription_text_box.setPlaceholderText("")
        self.reset_record_button()
        self.reset_model_download()

    def reset_record_button(self):
        self.record_button.setEnabled(True)

    def on_recording_amplitude_changed(self, amplitude: float):
        self.audio_meter_widget.update_amplitude(amplitude)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            # Second call after deferred close — proceed normally
            self._do_close()
            super().closeEvent(event)
            return

        if self.current_status == self.RecordingStatus.RECORDING:
            # Defer the close until the transcription thread finishes to avoid
            # blocking the GUI thread with a synchronous wait.
            event.ignore()
            self._closing = True

            if self.model_loader is not None:
                self.model_loader.cancel()

            self.stop_recording()

            # Connect to QThread.finished — the transcriber C++ object may already
            # be scheduled for deletion via deleteLater() by this point.
            thread = self.transcription_thread
            if thread is not None:
                try:
                    if thread.isRunning():
                        thread.finished.connect(self._on_close_transcriber_finished)
                    else:
                        self._on_close_transcriber_finished()
                except RuntimeError:
                    self._on_close_transcriber_finished()
            else:
                self._on_close_transcriber_finished()
            return

        self._do_close()
        super().closeEvent(event)

    def _on_close_transcriber_finished(self):
        self.transcription_thread = None
        self.close()

    def _do_close(self):
        #Close presentation window if open
        if self.presentation_window:
            self.presentation_window.close()
            self.presentation_window = None

        if self.recording_amplitude_listener is not None:
            self.recording_amplitude_listener.stop_recording()
            self.recording_amplitude_listener.deleteLater()
            self.recording_amplitude_listener = None

        if self.translator is not None:
            self.translator.stop()

        if self.translation_thread is not None:
            # Just request quit — do not block the GUI thread waiting for it
            self.translation_thread.quit()

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
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_ENABLE_LLM_TRANSLATION,
            self.transcription_options.enable_llm_translation,
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_LLM_MODEL,
            self.transcription_options.llm_model,
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_LLM_PROMPT,
            self.transcription_options.llm_prompt,
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_SILENCE_THRESHOLD,
            self.transcription_options.silence_threshold,
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_LINE_SEPARATOR,
            self.transcription_options.line_separator,
        )
