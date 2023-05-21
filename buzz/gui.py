import enum
import json
import logging
import sys
from enum import auto
from typing import Dict, List, Optional, Tuple

import sounddevice
from PyQt6 import QtGui
from PyQt6.QtCore import (QObject, Qt, QThread,
                          QTimer, QUrl, pyqtSignal, QModelIndex, QPoint,
                          QUrlQuery, QMetaObject, QEvent, QThreadPool)
from PyQt6.QtGui import (QAction, QCloseEvent, QDesktopServices, QIcon,
                         QKeySequence, QPixmap, QTextCursor, QValidator, QKeyEvent, QPainter, QColor)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QFileDialog, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
                             QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QGroupBox, QMenuBar, QFormLayout,
                             QAbstractItemView, QListWidget, QListWidgetItem, QSizePolicy)

from buzz.cache import TasksCache
from .__version__ import VERSION
from .action import Action
from .assets import get_asset_path
from .icon import Icon
from .locale import _
from .model_loader import WhisperModelSize, ModelType, TranscriptionModel, get_local_model_path, \
    ModelDownloader
from .paths import file_paths_as_title
from .recording import RecordingAmplitudeListener
from .settings.settings import Settings, APP_NAME
from .settings.shortcut import Shortcut
from .settings.shortcut_settings import ShortcutSettings
from .store.keyring_store import KeyringStore
from .transcriber import (SUPPORTED_OUTPUT_FORMATS, FileTranscriptionOptions, OutputFormat,
                          Task,
                          TranscriptionOptions,
                          FileTranscriberQueueWorker, FileTranscriptionTask, RecordingTranscriber, LOADED_WHISPER_DLL,
                          DEFAULT_WHISPER_TEMPERATURE, LANGUAGES)
from .widgets.line_edit import LineEdit
from .widgets.model_download_progress_dialog import ModelDownloadProgressDialog
from .widgets.model_type_combo_box import ModelTypeComboBox
from .widgets.openai_api_key_line_edit import OpenAIAPIKeyLineEdit
from .widgets.preferences_dialog import PreferencesDialog
from .widgets.toolbar import ToolBar
from .widgets.transcription_tasks_table_widget import TranscriptionTasksTableWidget
from .widgets.transcription_viewer_widget import TranscriptionViewerWidget


class FormLabel(QLabel):
    def __init__(self, name: str, parent: Optional[QWidget], *args) -> None:
        super().__init__(name, parent, *args)
        self.setStyleSheet('QLabel { text-align: right; }')
        self.setAlignment(Qt.AlignmentFlag(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight))


class AudioDevicesComboBox(QComboBox):
    """AudioDevicesComboBox displays a list of available audio input devices"""
    device_changed = pyqtSignal(int)
    audio_devices: List[Tuple[int, str]]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.audio_devices = self.get_audio_devices()
        self.addItems([device[1] for device in self.audio_devices])
        self.currentIndexChanged.connect(self.on_index_changed)

        default_device_id = self.get_default_device_id()
        if default_device_id != -1:
            for i, device in enumerate(self.audio_devices):
                if device[0] == default_device_id:
                    self.setCurrentIndex(i)

    def get_audio_devices(self) -> List[Tuple[int, str]]:
        try:
            devices: sounddevice.DeviceList = sounddevice.query_devices()
            return [(device.get('index'), device.get('name'))
                    for device in devices if device.get('max_input_channels') > 0]
        except UnicodeDecodeError:
            QMessageBox.critical(
                self, '',
                'An error occurred while loading your audio devices. Please check the application logs for more '
                'information.')
            return []

    def on_index_changed(self, index: int):
        self.device_changed.emit(self.audio_devices[index][0])

    def get_default_device_id(self) -> Optional[int]:
        default_system_device = sounddevice.default.device[0]
        if default_system_device != -1:
            return default_system_device

        audio_devices = self.get_audio_devices()
        if len(audio_devices) > 0:
            return audio_devices[0][0]

        return -1


class LanguagesComboBox(QComboBox):
    """LanguagesComboBox displays a list of languages available to use with Whisper"""
    # language is a language key from whisper.tokenizer.LANGUAGES or '' for "detect language"
    languageChanged = pyqtSignal(str)

    def __init__(self, default_language: Optional[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        whisper_languages = sorted(
            [(lang, LANGUAGES[lang].title()) for lang in LANGUAGES], key=lambda lang: lang[1])
        self.languages = [('', _('Detect Language'))] + whisper_languages

        self.addItems([lang[1] for lang in self.languages])
        self.currentIndexChanged.connect(self.on_index_changed)

        default_language_key = default_language if default_language != '' else None
        for i, lang in enumerate(self.languages):
            if lang[0] == default_language_key:
                self.setCurrentIndex(i)

    def on_index_changed(self, index: int):
        self.languageChanged.emit(self.languages[index][0])


class TasksComboBox(QComboBox):
    """TasksComboBox displays a list of tasks available to use with Whisper"""
    taskChanged = pyqtSignal(Task)

    def __init__(self, default_task: Task, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.tasks = [i for i in Task]
        self.addItems(map(lambda task: task.value.title(), self.tasks))
        self.currentIndexChanged.connect(self.on_index_changed)
        self.setCurrentText(default_task.value.title())

    def on_index_changed(self, index: int):
        self.taskChanged.emit(self.tasks[index])


class TextDisplayBox(QPlainTextEdit):
    """TextDisplayBox is a read-only textbox"""

    def __init__(self, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.setReadOnly(True)


class RecordButton(QPushButton):
    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__(_("Record"), parent)
        self.setDefault(True)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))

    def set_stopped(self):
        self.setText(_('Record'))
        self.setDefault(True)

    def set_recording(self):
        self.setText(_('Stop'))
        self.setDefault(False)


def show_model_download_error_dialog(parent: QWidget, error: str):
    message = parent.tr(
        'An error occurred while loading the Whisper model') + \
              f": {error}{'' if error.endswith('.') else '.'}" + \
              parent.tr("Please retry or check the application logs for more information.")

    QMessageBox.critical(parent, '', message)


class FileTranscriberWidget(QWidget):
    model_download_progress_dialog: Optional[ModelDownloadProgressDialog] = None
    model_loader: Optional[ModelDownloader] = None
    file_transcription_options: FileTranscriptionOptions
    transcription_options: TranscriptionOptions
    is_transcribing = False
    # (TranscriptionOptions, FileTranscriptionOptions, str)
    triggered = pyqtSignal(tuple)
    openai_access_token_changed = pyqtSignal(str)
    settings = Settings()

    def __init__(self, file_paths: List[str], parent: Optional[QWidget] = None,
                 flags: Qt.WindowType = Qt.WindowType.Widget) -> None:
        super().__init__(parent, flags)

        self.setWindowTitle(file_paths_as_title(file_paths))

        openai_access_token = KeyringStore().get_password(KeyringStore.Key.OPENAI_API_KEY)

        self.file_paths = file_paths
        default_language = self.settings.value(key=Settings.Key.FILE_TRANSCRIBER_LANGUAGE, default_value='')
        self.transcription_options = TranscriptionOptions(
            openai_access_token=openai_access_token,
            model=self.settings.value(key=Settings.Key.FILE_TRANSCRIBER_MODEL, default_value=TranscriptionModel()),
            task=self.settings.value(key=Settings.Key.FILE_TRANSCRIBER_TASK, default_value=Task.TRANSCRIBE),
            language=default_language if default_language != '' else None,
            initial_prompt=self.settings.value(key=Settings.Key.FILE_TRANSCRIBER_INITIAL_PROMPT, default_value=''),
            temperature=self.settings.value(key=Settings.Key.FILE_TRANSCRIBER_TEMPERATURE,
                                            default_value=DEFAULT_WHISPER_TEMPERATURE),
            word_level_timings=self.settings.value(key=Settings.Key.FILE_TRANSCRIBER_WORD_LEVEL_TIMINGS,
                                                   default_value=False))
        self.file_transcription_options = FileTranscriptionOptions(
            file_paths=self.file_paths)

        layout = QVBoxLayout(self)

        transcription_options_group_box = TranscriptionOptionsGroupBox(
            default_transcription_options=self.transcription_options, parent=self)
        transcription_options_group_box.transcription_options_changed.connect(
            self.on_transcription_options_changed)

        self.word_level_timings_checkbox = QCheckBox(_('Word-level timings'))
        self.word_level_timings_checkbox.setChecked(
            self.settings.value(key=Settings.Key.FILE_TRANSCRIBER_WORD_LEVEL_TIMINGS, default_value=False))
        self.word_level_timings_checkbox.stateChanged.connect(
            self.on_word_level_timings_changed)

        file_transcription_layout = QFormLayout()
        file_transcription_layout.addRow('', self.word_level_timings_checkbox)

        export_format_layout = QHBoxLayout()
        default_export_format_states: List[str] = self.settings.value(key=Settings.Key.FILE_TRANSCRIBER_EXPORT_FORMATS,
                                                                      default_value=[])
        for output_format in OutputFormat:
            export_format_checkbox = QCheckBox(f'{output_format.value.upper()}', parent=self)
            export_format_checkbox.setChecked(output_format.value in default_export_format_states)
            export_format_checkbox.stateChanged.connect(self.get_on_checkbox_state_changed_callback(output_format))
            export_format_layout.addWidget(export_format_checkbox)

        file_transcription_layout.addRow('Export:', export_format_layout)

        self.run_button = QPushButton(_('Run'), self)
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.on_click_run)

        layout.addWidget(transcription_options_group_box)
        layout.addLayout(file_transcription_layout)
        layout.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignRight)

        self.setLayout(layout)
        self.setFixedSize(self.sizeHint())

    def get_on_checkbox_state_changed_callback(self, output_format: OutputFormat):
        def on_checkbox_state_changed(state: int):
            if state == Qt.CheckState.Checked.value:
                self.file_transcription_options.output_formats.add(output_format)
            elif state == Qt.CheckState.Unchecked.value:
                self.file_transcription_options.output_formats.remove(output_format)

        return on_checkbox_state_changed

    def on_transcription_options_changed(self, transcription_options: TranscriptionOptions):
        self.transcription_options = transcription_options
        self.word_level_timings_checkbox.setDisabled(
            self.transcription_options.model.model_type == ModelType.HUGGING_FACE or self.transcription_options.model.model_type == ModelType.OPEN_AI_WHISPER_API)
        if self.transcription_options.openai_access_token != '':
            self.openai_access_token_changed.emit(self.transcription_options.openai_access_token)

    def on_click_run(self):
        self.run_button.setDisabled(True)

        model_path = get_local_model_path(model=self.transcription_options.model)
        if model_path is not None:
            self.on_model_loaded(model_path)
            return

        self.model_loader = ModelDownloader(model=self.transcription_options.model)
        self.model_loader.signals.progress.connect(self.on_download_model_progress)
        self.model_loader.signals.error.connect(self.on_download_model_error)
        self.model_loader.signals.finished.connect(self.on_model_loaded)
        QThreadPool().globalInstance().start(self.model_loader)

    def on_model_loaded(self, model_path: str):
        self.reset_transcriber_controls()

        self.triggered.emit((self.transcription_options,
                             self.file_transcription_options, model_path))
        self.close()

    def on_download_model_progress(self, progress: Tuple[float, float]):
        (current_size, total_size) = progress

        if self.model_download_progress_dialog is None:
            self.model_download_progress_dialog = ModelDownloadProgressDialog(
                model_type=self.transcription_options.model.model_type, parent=self)
            self.model_download_progress_dialog.canceled.connect(
                self.on_cancel_model_progress_dialog)

        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.set_value(fraction_completed=current_size / total_size)

    def on_download_model_error(self, error: str):
        self.reset_model_download()
        show_model_download_error_dialog(self, error)
        self.reset_transcriber_controls()

    def reset_transcriber_controls(self):
        self.run_button.setDisabled(False)

    def on_cancel_model_progress_dialog(self):
        if self.model_loader is not None:
            self.model_loader.cancel()
        self.reset_model_download()

    def reset_model_download(self):
        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.close()
            self.model_download_progress_dialog = None

    def on_word_level_timings_changed(self, value: int):
        self.transcription_options.word_level_timings = value == Qt.CheckState.Checked.value

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.model_loader is not None:
            self.model_loader.cancel()

        self.settings.set_value(Settings.Key.FILE_TRANSCRIBER_LANGUAGE, self.transcription_options.language)
        self.settings.set_value(Settings.Key.FILE_TRANSCRIBER_TASK, self.transcription_options.task)
        self.settings.set_value(Settings.Key.FILE_TRANSCRIBER_TEMPERATURE, self.transcription_options.temperature)
        self.settings.set_value(Settings.Key.FILE_TRANSCRIBER_INITIAL_PROMPT, self.transcription_options.initial_prompt)
        self.settings.set_value(Settings.Key.FILE_TRANSCRIBER_MODEL, self.transcription_options.model)
        self.settings.set_value(key=Settings.Key.FILE_TRANSCRIBER_WORD_LEVEL_TIMINGS,
                                value=self.transcription_options.word_level_timings)
        self.settings.set_value(key=Settings.Key.FILE_TRANSCRIBER_EXPORT_FORMATS,
                                value=[export_format.value for export_format in
                                       self.file_transcription_options.output_formats])

        super().closeEvent(event)


class AdvancedSettingsButton(QPushButton):
    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__('Advanced...', parent)


class AudioMeterWidget(QWidget):
    current_amplitude: float
    BAR_WIDTH = 2
    BAR_MARGIN = 1
    BAR_INACTIVE_COLOR: QColor
    BAR_ACTIVE_COLOR: QColor

    # Factor by which the amplitude is scaled to make the changes more visible
    DIFF_MULTIPLIER_FACTOR = 10
    SMOOTHING_FACTOR = 0.95

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumWidth(10)
        self.setFixedHeight(16)

        # Extra padding to fix layout
        self.PADDING_TOP = 3

        self.current_amplitude = 0.0

        self.MINIMUM_AMPLITUDE = 0.00005  # minimum amplitude to show the first bar
        self.AMPLITUDE_SCALE_FACTOR = 15  # scale the amplitudes such that 1/AMPLITUDE_SCALE_FACTOR will show all bars

        if self.palette().window().color().black() > 127:
            self.BAR_INACTIVE_COLOR = QColor('#555')
            self.BAR_ACTIVE_COLOR = QColor('#999')
        else:
            self.BAR_INACTIVE_COLOR = QColor('#BBB')
            self.BAR_ACTIVE_COLOR = QColor('#555')

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)

        rect = self.rect()
        center_x = rect.center().x()
        num_bars_in_half = int((rect.width() / 2) / (self.BAR_MARGIN + self.BAR_WIDTH))
        for i in range(num_bars_in_half):
            is_bar_active = ((self.current_amplitude - self.MINIMUM_AMPLITUDE) * self.AMPLITUDE_SCALE_FACTOR) > (
                    i / num_bars_in_half)
            painter.setBrush(self.BAR_ACTIVE_COLOR if is_bar_active else self.BAR_INACTIVE_COLOR)

            # draw to left
            painter.drawRect(center_x - ((i + 1) * (self.BAR_MARGIN + self.BAR_WIDTH)), rect.top() + self.PADDING_TOP,
                             self.BAR_WIDTH,
                             rect.height() - self.PADDING_TOP)
            # draw to right
            painter.drawRect(center_x + (self.BAR_MARGIN + (i * (self.BAR_MARGIN + self.BAR_WIDTH))),
                             rect.top() + self.PADDING_TOP,
                             self.BAR_WIDTH, rect.height() - self.PADDING_TOP)

    def update_amplitude(self, amplitude: float):
        self.current_amplitude = max(amplitude, self.current_amplitude * self.SMOOTHING_FACTOR)
        self.repaint()


class RecordingTranscriberWidget(QWidget):
    current_status: 'RecordingStatus'
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

    def __init__(self, parent: Optional[QWidget] = None, flags: Optional[Qt.WindowType] = None) -> None:
        super().__init__(parent)

        if flags is not None:
            self.setWindowFlags(flags)

        layout = QVBoxLayout(self)

        self.current_status = self.RecordingStatus.STOPPED
        self.setWindowTitle(_('Live Recording'))

        self.settings = Settings()
        default_language = self.settings.value(key=Settings.Key.RECORDING_TRANSCRIBER_LANGUAGE, default_value='')
        self.transcription_options = TranscriptionOptions(
            model=self.settings.value(key=Settings.Key.RECORDING_TRANSCRIBER_MODEL, default_value=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP if LOADED_WHISPER_DLL else ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY)),
            task=self.settings.value(key=Settings.Key.RECORDING_TRANSCRIBER_TASK, default_value=Task.TRANSCRIBE),
            language=default_language if default_language != '' else None,
            initial_prompt=self.settings.value(key=Settings.Key.RECORDING_TRANSCRIBER_INITIAL_PROMPT, default_value=''),
            temperature=self.settings.value(key=Settings.Key.RECORDING_TRANSCRIBER_TEMPERATURE,
                                            default_value=DEFAULT_WHISPER_TEMPERATURE), word_level_timings=False)

        self.audio_devices_combo_box = AudioDevicesComboBox(self)
        self.audio_devices_combo_box.device_changed.connect(
            self.on_device_changed)
        self.selected_device_id = self.audio_devices_combo_box.get_default_device_id()

        self.record_button = RecordButton(self)
        self.record_button.clicked.connect(self.on_record_button_clicked)

        self.text_box = TextDisplayBox(self)
        self.text_box.setPlaceholderText(_('Click Record to begin...'))

        transcription_options_group_box = TranscriptionOptionsGroupBox(
            default_transcription_options=self.transcription_options,
            # Live transcription with OpenAI Whisper API not implemented
            model_types=[model_type for model_type in ModelType if model_type is not ModelType.OPEN_AI_WHISPER_API],
            parent=self)
        transcription_options_group_box.transcription_options_changed.connect(
            self.on_transcription_options_changed)

        recording_options_layout = QFormLayout()
        recording_options_layout.addRow(
            _('Microphone:'), self.audio_devices_combo_box)

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

    def on_transcription_options_changed(self, transcription_options: TranscriptionOptions):
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
        self.device_sample_rate = RecordingTranscriber.get_device_sample_rate(self.selected_device_id)

        self.recording_amplitude_listener = RecordingAmplitudeListener(input_device_index=self.selected_device_id,
                                                                       parent=self)
        self.recording_amplitude_listener.amplitude_changed.connect(self.on_recording_amplitude_changed)
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

        model_path = get_local_model_path(model=self.transcription_options.model)
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
        self.transcriber = RecordingTranscriber(input_device_index=self.selected_device_id,
                                                sample_rate=self.device_sample_rate,
                                                transcription_options=self.transcription_options,
                                                model_path=model_path)

        self.transcriber.moveToThread(self.transcription_thread)

        self.transcription_thread.started.connect(self.transcriber.start)
        self.transcription_thread.finished.connect(
            self.transcription_thread.deleteLater)

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
                model_type=self.transcription_options.model.model_type, parent=self)
            self.model_download_progress_dialog.canceled.connect(
                self.on_cancel_model_progress_dialog)

        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.set_value(fraction_completed=current_size / total_size)

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
                self.text_box.insertPlainText('\n\n')
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
            self, '',
            _('An error occurred while starting a new recording:') + error + '. ' +
            _('Please check your audio devices or check the application logs for more information.'))

    def on_cancel_model_progress_dialog(self):
        if self.model_loader is not None:
            self.model_loader.stop()
        self.reset_model_download()
        self.set_recording_status_stopped()
        self.record_button.setDisabled(False)

    def reset_model_download(self):
        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.close()
            self.model_download_progress_dialog = None

    def reset_recording_controls(self):
        # Clear text box placeholder because the first chunk takes a while to process
        self.text_box.setPlaceholderText('')
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

        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_LANGUAGE, self.transcription_options.language)
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_TASK, self.transcription_options.task)
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_TEMPERATURE, self.transcription_options.temperature)
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_INITIAL_PROMPT,
                                self.transcription_options.initial_prompt)
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_MODEL, self.transcription_options.model)

        return super().closeEvent(event)


BUZZ_ICON_PATH = get_asset_path('assets/buzz.ico')
BUZZ_LARGE_ICON_PATH = get_asset_path('assets/buzz-icon-1024.png')
RECORD_ICON_PATH = get_asset_path('assets/mic_FILL0_wght700_GRAD0_opsz48.svg')
EXPAND_ICON_PATH = get_asset_path('assets/open_in_full_FILL0_wght700_GRAD0_opsz48.svg')
ADD_ICON_PATH = get_asset_path('assets/add_FILL0_wght700_GRAD0_opsz48.svg')
TRASH_ICON_PATH = get_asset_path('assets/delete_FILL0_wght700_GRAD0_opsz48.svg')
CANCEL_ICON_PATH = get_asset_path('assets/cancel_FILL0_wght700_GRAD0_opsz48.svg')


class AboutDialog(QDialog):
    GITHUB_API_LATEST_RELEASE_URL = 'https://api.github.com/repos/chidiwilliams/buzz/releases/latest'
    GITHUB_LATEST_RELEASE_URL = 'https://github.com/chidiwilliams/buzz/releases/latest'

    def __init__(self, network_access_manager: Optional[QNetworkAccessManager] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowIcon(QIcon(BUZZ_ICON_PATH))
        self.setWindowTitle(f'{_("About")} {APP_NAME}')

        if network_access_manager is None:
            network_access_manager = QNetworkAccessManager()

        self.network_access_manager = network_access_manager
        self.network_access_manager.finished.connect(self.on_latest_release_reply)

        layout = QVBoxLayout(self)

        image_label = QLabel()
        pixmap = QPixmap(BUZZ_LARGE_ICON_PATH).scaled(
            80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignmentFlag(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter))

        buzz_label = QLabel(APP_NAME)
        buzz_label.setAlignment(Qt.AlignmentFlag(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter))
        buzz_label_font = QtGui.QFont()
        buzz_label_font.setBold(True)
        buzz_label_font.setPointSize(20)
        buzz_label.setFont(buzz_label_font)

        version_label = QLabel(f"{_('Version')} {VERSION}")
        version_label.setAlignment(Qt.AlignmentFlag(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter))

        self.check_updates_button = QPushButton(_('Check for updates'), self)
        self.check_updates_button.clicked.connect(self.on_click_check_for_updates)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton(
            QDialogButtonBox.StandardButton.Close), self)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(image_label)
        layout.addWidget(buzz_label)
        layout.addWidget(version_label)
        layout.addWidget(self.check_updates_button)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def on_click_check_for_updates(self):
        url = QUrl(self.GITHUB_API_LATEST_RELEASE_URL)
        self.network_access_manager.get(QNetworkRequest(url))
        self.check_updates_button.setDisabled(True)

    def on_latest_release_reply(self, reply: QNetworkReply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            response = json.loads(reply.readAll().data())
            tag_name = response.get('name')
            if self.is_version_lower(VERSION, tag_name[1:]):
                QDesktopServices.openUrl(QUrl(self.GITHUB_LATEST_RELEASE_URL))
            else:
                QMessageBox.information(self, '', _("You're up to date!"))
        self.check_updates_button.setEnabled(True)

    @staticmethod
    def is_version_lower(version_a: str, version_b: str):
        return version_a.replace('.', '') < version_b.replace('.', '')


class MainWindowToolbar(ToolBar):
    new_transcription_action_triggered: pyqtSignal
    open_transcript_action_triggered: pyqtSignal
    clear_history_action_triggered: pyqtSignal
    ICON_LIGHT_THEME_BACKGROUND = '#555'
    ICON_DARK_THEME_BACKGROUND = '#AAA'

    def __init__(self, shortcuts: Dict[str, str], parent: Optional[QWidget]):
        super().__init__(parent)

        self.record_action = Action(Icon(RECORD_ICON_PATH, self), _('Record'), self)
        self.record_action.triggered.connect(self.on_record_action_triggered)

        self.new_transcription_action = Action(Icon(ADD_ICON_PATH, self), _('New Transcription'), self)
        self.new_transcription_action_triggered = self.new_transcription_action.triggered

        self.open_transcript_action = Action(Icon(EXPAND_ICON_PATH, self),
                                             _('Open Transcript'), self)
        self.open_transcript_action_triggered = self.open_transcript_action.triggered
        self.open_transcript_action.setDisabled(True)

        self.stop_transcription_action = Action(Icon(CANCEL_ICON_PATH, self), _('Cancel Transcription'), self)
        self.stop_transcription_action_triggered = self.stop_transcription_action.triggered
        self.stop_transcription_action.setDisabled(True)

        self.clear_history_action = Action(Icon(TRASH_ICON_PATH, self), _('Clear History'), self)
        self.clear_history_action_triggered = self.clear_history_action.triggered
        self.clear_history_action.setDisabled(True)

        self.set_shortcuts(shortcuts)

        self.addAction(self.record_action)
        self.addSeparator()
        self.addActions([self.new_transcription_action, self.open_transcript_action, self.stop_transcription_action,
                         self.clear_history_action])
        self.setMovable(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

    def set_shortcuts(self, shortcuts: Dict[str, str]):
        self.record_action.setShortcut(QKeySequence.fromString(shortcuts[Shortcut.OPEN_RECORD_WINDOW.name]))
        self.new_transcription_action.setShortcut(QKeySequence.fromString(shortcuts[Shortcut.OPEN_IMPORT_WINDOW.name]))
        self.open_transcript_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.OPEN_TRANSCRIPT_EDITOR.name]))
        self.stop_transcription_action.setShortcut(QKeySequence.fromString(shortcuts[Shortcut.STOP_TRANSCRIPTION.name]))
        self.clear_history_action.setShortcut(QKeySequence.fromString(shortcuts[Shortcut.CLEAR_HISTORY.name]))

    def on_record_action_triggered(self):
        recording_transcriber_window = RecordingTranscriberWidget(self, flags=Qt.WindowType.Window)
        recording_transcriber_window.show()

    def set_stop_transcription_action_enabled(self, enabled: bool):
        self.stop_transcription_action.setEnabled(enabled)

    def set_open_transcript_action_enabled(self, enabled: bool):
        self.open_transcript_action.setEnabled(enabled)

    def set_clear_history_action_enabled(self, enabled: bool):
        self.clear_history_action.setEnabled(enabled)


class MainWindow(QMainWindow):
    table_widget: TranscriptionTasksTableWidget
    tasks: Dict[int, 'FileTranscriptionTask']
    tasks_changed = pyqtSignal()
    openai_access_token: Optional[str]

    def __init__(self, tasks_cache=TasksCache()):
        super().__init__(flags=Qt.WindowType.Window)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(BUZZ_ICON_PATH))
        self.setMinimumSize(450, 400)

        self.setAcceptDrops(True)

        self.tasks_cache = tasks_cache

        self.settings = Settings()

        self.shortcut_settings = ShortcutSettings(settings=self.settings)
        self.shortcuts = self.shortcut_settings.load()

        self.tasks = {}
        self.tasks_changed.connect(self.on_tasks_changed)

        self.toolbar = MainWindowToolbar(shortcuts=self.shortcuts, parent=self)
        self.toolbar.new_transcription_action_triggered.connect(self.on_new_transcription_action_triggered)
        self.toolbar.open_transcript_action_triggered.connect(self.open_transcript_viewer)
        self.toolbar.clear_history_action_triggered.connect(self.on_clear_history_action_triggered)
        self.toolbar.stop_transcription_action_triggered.connect(self.on_stop_transcription_action_triggered)
        self.addToolBar(self.toolbar)
        self.setUnifiedTitleAndToolBarOnMac(True)

        self.menu_bar = MenuBar(shortcuts=self.shortcuts, parent=self)
        self.menu_bar.import_action_triggered.connect(
            self.on_new_transcription_action_triggered)
        self.menu_bar.shortcuts_changed.connect(self.on_shortcuts_changed)
        self.menu_bar.openai_api_key_changed.connect(self.on_openai_access_token_changed)
        self.setMenuBar(self.menu_bar)

        self.table_widget = TranscriptionTasksTableWidget(self)
        self.table_widget.doubleClicked.connect(self.on_table_double_clicked)
        self.table_widget.return_clicked.connect(self.open_transcript_viewer)
        self.table_widget.itemSelectionChanged.connect(
            self.on_table_selection_changed)

        self.setCentralWidget(self.table_widget)

        # Start transcriber thread
        self.transcriber_thread = QThread()

        self.transcriber_worker = FileTranscriberQueueWorker()
        self.transcriber_worker.moveToThread(self.transcriber_thread)

        self.transcriber_worker.task_updated.connect(
            self.update_task_table_row)
        self.transcriber_worker.completed.connect(self.transcriber_thread.quit)

        self.transcriber_thread.started.connect(self.transcriber_worker.run)

        self.transcriber_thread.start()

        self.load_tasks_from_cache()

    def dragEnterEvent(self, event):
        # Accept file drag events
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        file_paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self.open_file_transcriber_widget(file_paths=file_paths)

    def on_file_transcriber_triggered(self, options: Tuple[TranscriptionOptions, FileTranscriptionOptions, str]):
        transcription_options, file_transcription_options, model_path = options
        for file_path in file_transcription_options.file_paths:
            task = FileTranscriptionTask(
                file_path, transcription_options, file_transcription_options, model_path)
            self.add_task(task)

    def update_task_table_row(self, task: FileTranscriptionTask):
        self.table_widget.upsert_task(task)
        self.tasks[task.id] = task
        self.tasks_changed.emit()

    @staticmethod
    def task_completed_or_errored(task: FileTranscriptionTask):
        return task.status == FileTranscriptionTask.Status.COMPLETED or \
            task.status == FileTranscriptionTask.Status.FAILED

    def on_clear_history_action_triggered(self):
        selected_rows = self.table_widget.selectionModel().selectedRows()
        if len(selected_rows) == 0:
            return

        reply = QMessageBox.question(
            self, _('Clear History'),
            _('Are you sure you want to delete the selected transcription(s)? This action cannot be undone.'))
        if reply == QMessageBox.StandardButton.Yes:
            task_ids = [TranscriptionTasksTableWidget.find_task_id(selected_row) for selected_row in selected_rows]
            for task_id in task_ids:
                self.table_widget.clear_task(task_id)
                self.tasks.pop(task_id)
                self.tasks_changed.emit()

    def on_stop_transcription_action_triggered(self):
        selected_rows = self.table_widget.selectionModel().selectedRows()
        for selected_row in selected_rows:
            task_id = TranscriptionTasksTableWidget.find_task_id(selected_row)
            task = self.tasks[task_id]

            task.status = FileTranscriptionTask.Status.CANCELED
            self.tasks_changed.emit()
            self.transcriber_worker.cancel_task(task_id)
            self.table_widget.upsert_task(task)

    def on_new_transcription_action_triggered(self):
        (file_paths, __) = QFileDialog.getOpenFileNames(
            self, _('Select audio file'), '', SUPPORTED_OUTPUT_FORMATS)
        if len(file_paths) == 0:
            return

        self.open_file_transcriber_widget(file_paths)

    def open_file_transcriber_widget(self, file_paths: List[str]):
        file_transcriber_window = FileTranscriberWidget(file_paths=file_paths,
                                                        parent=self,
                                                        flags=Qt.WindowType.Window)
        file_transcriber_window.triggered.connect(
            self.on_file_transcriber_triggered)
        file_transcriber_window.openai_access_token_changed.connect(self.on_openai_access_token_changed)
        file_transcriber_window.show()

    @staticmethod
    def on_openai_access_token_changed(access_token: str):
        KeyringStore().set_password(KeyringStore.Key.OPENAI_API_KEY, access_token)

    def open_transcript_viewer(self):
        selected_rows = self.table_widget.selectionModel().selectedRows()
        for selected_row in selected_rows:
            task_id = TranscriptionTasksTableWidget.find_task_id(selected_row)
            self.open_transcription_viewer(task_id)

    def on_table_selection_changed(self):
        self.toolbar.set_open_transcript_action_enabled(self.should_enable_open_transcript_action())
        self.toolbar.set_stop_transcription_action_enabled(self.should_enable_stop_transcription_action())
        self.toolbar.set_clear_history_action_enabled(self.should_enable_clear_history_action())

    def should_enable_open_transcript_action(self):
        return self.selected_tasks_have_status([FileTranscriptionTask.Status.COMPLETED])

    def should_enable_stop_transcription_action(self):
        return self.selected_tasks_have_status(
            [FileTranscriptionTask.Status.IN_PROGRESS, FileTranscriptionTask.Status.QUEUED])

    def should_enable_clear_history_action(self):
        return self.selected_tasks_have_status(
            [FileTranscriptionTask.Status.COMPLETED, FileTranscriptionTask.Status.FAILED,
             FileTranscriptionTask.Status.CANCELED])

    def selected_tasks_have_status(self, statuses: List[FileTranscriptionTask.Status]):
        selected_rows = self.table_widget.selectionModel().selectedRows()
        if len(selected_rows) == 0:
            return False
        return all(
            [self.tasks[TranscriptionTasksTableWidget.find_task_id(selected_row)].status in statuses for selected_row in
             selected_rows])

    def on_table_double_clicked(self, index: QModelIndex):
        task_id = TranscriptionTasksTableWidget.find_task_id(index)
        self.open_transcription_viewer(task_id)

    def open_transcription_viewer(self, task_id: int):
        task = self.tasks[task_id]
        if task.status != FileTranscriptionTask.Status.COMPLETED:
            return

        transcription_viewer_widget = TranscriptionViewerWidget(
            transcription_task=task, parent=self, flags=Qt.WindowType.Window)
        transcription_viewer_widget.show()

    def add_task(self, task: FileTranscriptionTask):
        self.transcriber_worker.add_task(task)

    def load_tasks_from_cache(self):
        tasks = self.tasks_cache.load()
        for task in tasks:
            if task.status == FileTranscriptionTask.Status.QUEUED or \
                    task.status == FileTranscriptionTask.Status.IN_PROGRESS:
                task.status = None
                self.transcriber_worker.add_task(task)
            else:
                self.update_task_table_row(task)

    def save_tasks_to_cache(self):
        self.tasks_cache.save(list(self.tasks.values()))

    def on_tasks_changed(self):
        self.toolbar.set_open_transcript_action_enabled(self.should_enable_open_transcript_action())
        self.toolbar.set_stop_transcription_action_enabled(self.should_enable_stop_transcription_action())
        self.toolbar.set_clear_history_action_enabled(self.should_enable_clear_history_action())
        self.save_tasks_to_cache()

    def on_shortcuts_changed(self, shortcuts: dict):
        self.shortcuts = shortcuts
        self.menu_bar.set_shortcuts(shortcuts=self.shortcuts)
        self.toolbar.set_shortcuts(shortcuts=self.shortcuts)
        self.shortcut_settings.save(shortcuts=self.shortcuts)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.transcriber_worker.stop()
        self.transcriber_thread.quit()
        self.transcriber_thread.wait()
        self.save_tasks_to_cache()
        self.shortcut_settings.save(shortcuts=self.shortcuts)
        super().closeEvent(event)


# Adapted from https://github.com/ismailsunni/scripts/blob/master/autocomplete_from_url.py
class HuggingFaceSearchLineEdit(LineEdit):
    model_selected = pyqtSignal(str)
    popup: QListWidget

    def __init__(self, network_access_manager: Optional[QNetworkAccessManager] = None,
                 parent: Optional[QWidget] = None):
        super().__init__('', parent)

        self.setMinimumWidth(150)
        self.setPlaceholderText('openai/whisper-tiny')

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.fetch_models)

        # Restart debounce timer each time editor text changes
        self.textEdited.connect(self.timer.start)
        self.textEdited.connect(self.on_text_edited)

        if network_access_manager is None:
            network_access_manager = QNetworkAccessManager(self)

        self.network_manager = network_access_manager
        self.network_manager.finished.connect(self.on_request_response)

        self.popup = QListWidget()
        self.popup.setWindowFlags(Qt.WindowType.Popup)
        self.popup.setFocusProxy(self)
        self.popup.setMouseTracking(True)
        self.popup.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.popup.installEventFilter(self)
        self.popup.itemClicked.connect(self.on_select_item)

    def on_text_edited(self, text: str):
        self.model_selected.emit(text)

    def on_select_item(self):
        self.popup.hide()
        self.setFocus()

        item = self.popup.currentItem()
        self.setText(item.text())
        QMetaObject.invokeMethod(self, 'returnPressed')
        self.model_selected.emit(item.data(Qt.ItemDataRole.UserRole))

    def fetch_models(self):
        text = self.text()
        if len(text) < 3:
            return

        url = QUrl("https://huggingface.co/api/models")

        query = QUrlQuery()
        query.addQueryItem("filter", "whisper")
        query.addQueryItem("search", text)

        url.setQuery(query)

        return self.network_manager.get(QNetworkRequest(url))

    def on_popup_selected(self):
        self.timer.stop()

    def on_request_response(self, network_reply: QNetworkReply):
        if network_reply.error() != QNetworkReply.NetworkError.NoError:
            logging.debug('Error fetching Hugging Face models: %s', network_reply.error())
            return

        models = json.loads(network_reply.readAll().data())

        self.popup.setUpdatesEnabled(False)
        self.popup.clear()

        for model in models:
            model_id = model.get('id')

            item = QListWidgetItem(self.popup)
            item.setText(model_id)
            item.setData(Qt.ItemDataRole.UserRole, model_id)

        self.popup.setCurrentItem(self.popup.item(0))
        self.popup.setFixedWidth(self.popup.sizeHintForColumn(0) + 20)
        self.popup.setFixedHeight(self.popup.sizeHintForRow(0) * min(len(models), 8))  # show max 8 models, then scroll
        self.popup.setUpdatesEnabled(True)
        self.popup.move(self.mapToGlobal(QPoint(0, self.height())))
        self.popup.setFocus()
        self.popup.show()

    def eventFilter(self, target: QObject, event: QEvent):
        if hasattr(self, 'popup') is False or target != self.popup:
            return False

        if event.type() == QEvent.Type.MouseButtonPress:
            self.popup.hide()
            self.setFocus()
            return True

        if isinstance(event, QKeyEvent):
            key = event.key()
            if key in [Qt.Key.Key_Enter, Qt.Key.Key_Return]:
                if self.popup.currentItem() is not None:
                    self.on_select_item()
                return True

            if key == Qt.Key.Key_Escape:
                self.setFocus()
                self.popup.hide()
                return True

            if key in [Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp,
                       Qt.Key.Key_PageDown]:
                return False

            self.setFocus()
            self.event(event)
            self.popup.hide()

        return False


class TranscriptionOptionsGroupBox(QGroupBox):
    transcription_options: TranscriptionOptions
    transcription_options_changed = pyqtSignal(TranscriptionOptions)

    def __init__(self, default_transcription_options: TranscriptionOptions = TranscriptionOptions(),
                 model_types: Optional[List[ModelType]] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(title='', parent=parent)
        self.transcription_options = default_transcription_options

        self.form_layout = QFormLayout(self)

        self.tasks_combo_box = TasksComboBox(
            default_task=self.transcription_options.task,
            parent=self)
        self.tasks_combo_box.taskChanged.connect(self.on_task_changed)

        self.languages_combo_box = LanguagesComboBox(
            default_language=self.transcription_options.language,
            parent=self)
        self.languages_combo_box.languageChanged.connect(
            self.on_language_changed)

        self.advanced_settings_button = AdvancedSettingsButton(self)
        self.advanced_settings_button.clicked.connect(
            self.open_advanced_settings)

        self.hugging_face_search_line_edit = HuggingFaceSearchLineEdit()
        self.hugging_face_search_line_edit.model_selected.connect(self.on_hugging_face_model_changed)

        self.model_type_combo_box = ModelTypeComboBox(model_types=model_types,
                                                      default_model=default_transcription_options.model.model_type,
                                                      parent=self)
        self.model_type_combo_box.changed.connect(self.on_model_type_changed)

        self.whisper_model_size_combo_box = QComboBox(self)
        self.whisper_model_size_combo_box.addItems([size.value.title() for size in WhisperModelSize])
        if default_transcription_options.model.whisper_model_size is not None:
            self.whisper_model_size_combo_box.setCurrentText(
                default_transcription_options.model.whisper_model_size.value.title())
        self.whisper_model_size_combo_box.currentTextChanged.connect(self.on_whisper_model_size_changed)

        self.openai_access_token_edit = OpenAIAPIKeyLineEdit(key=default_transcription_options.openai_access_token,
                                                             parent=self)
        self.openai_access_token_edit.key_changed.connect(self.on_openai_access_token_edit_changed)

        self.form_layout.addRow(_('Model:'), self.model_type_combo_box)
        self.form_layout.addRow('', self.whisper_model_size_combo_box)
        self.form_layout.addRow('', self.hugging_face_search_line_edit)
        self.form_layout.addRow('Access Token:', self.openai_access_token_edit)
        self.form_layout.addRow(_('Task:'), self.tasks_combo_box)
        self.form_layout.addRow(_('Language:'), self.languages_combo_box)

        self.reset_visible_rows()

        self.form_layout.addRow('', self.advanced_settings_button)

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
            transcription_options=self.transcription_options, parent=self)
        dialog.transcription_options_changed.connect(
            self.on_transcription_options_changed)
        dialog.exec()

    def on_transcription_options_changed(self, transcription_options: TranscriptionOptions):
        self.transcription_options = transcription_options
        self.transcription_options_changed.emit(transcription_options)

    def reset_visible_rows(self):
        model_type = self.transcription_options.model.model_type
        self.form_layout.setRowVisible(self.hugging_face_search_line_edit, model_type == ModelType.HUGGING_FACE)
        self.form_layout.setRowVisible(self.whisper_model_size_combo_box,
                                       (model_type == ModelType.WHISPER) or (model_type == ModelType.WHISPER_CPP) or (
                                               model_type == ModelType.FASTER_WHISPER))
        self.form_layout.setRowVisible(self.openai_access_token_edit, model_type == ModelType.OPEN_AI_WHISPER_API)

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


class MenuBar(QMenuBar):
    import_action_triggered = pyqtSignal()
    shortcuts_changed = pyqtSignal(dict)
    openai_api_key_changed = pyqtSignal(str)

    def __init__(self, shortcuts: Dict[str, str], parent: QWidget):
        super().__init__(parent)

        self.shortcuts = shortcuts

        self.import_action = QAction(_("Import Media File..."), self)
        self.import_action.triggered.connect(
            self.on_import_action_triggered)

        about_action = QAction(f'{_("About")} {APP_NAME}', self)
        about_action.triggered.connect(self.on_about_action_triggered)

        self.preferences_action = QAction(_("Preferences..."), self)
        self.preferences_action.triggered.connect(self.on_preferences_action_triggered)

        self.set_shortcuts(shortcuts)

        file_menu = self.addMenu(_("File"))
        file_menu.addAction(self.import_action)

        help_menu = self.addMenu(_("Help"))
        help_menu.addAction(about_action)
        help_menu.addAction(self.preferences_action)

    def on_import_action_triggered(self):
        self.import_action_triggered.emit()

    def on_about_action_triggered(self):
        about_dialog = AboutDialog(parent=self)
        about_dialog.open()

    def on_preferences_action_triggered(self):
        preferences_dialog = PreferencesDialog(shortcuts=self.shortcuts, parent=self)
        preferences_dialog.shortcuts_changed.connect(self.shortcuts_changed)
        preferences_dialog.openai_api_key_changed.connect(self.openai_api_key_changed)
        preferences_dialog.open()

    def set_shortcuts(self, shortcuts: Dict[str, str]):
        self.shortcuts = shortcuts

        self.import_action.setShortcut(QKeySequence.fromString(shortcuts[Shortcut.OPEN_IMPORT_WINDOW.name]))
        self.preferences_action.setShortcut(QKeySequence.fromString(shortcuts[Shortcut.OPEN_PREFERENCES_WINDOW.name]))


class Application(QApplication):
    window: MainWindow

    def __init__(self) -> None:
        super().__init__(sys.argv)

        self.setApplicationName(APP_NAME)
        self.setApplicationVersion(VERSION)

        self.window = MainWindow()
        self.window.show()

    def add_task(self, task: FileTranscriptionTask):
        self.window.add_task(task)


class AdvancedSettingsDialog(QDialog):
    transcription_options: TranscriptionOptions
    transcription_options_changed = pyqtSignal(TranscriptionOptions)

    def __init__(self, transcription_options: TranscriptionOptions, parent: QWidget | None = None):
        super().__init__(parent)

        self.transcription_options = transcription_options

        self.setWindowTitle(_('Advanced Settings'))

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton(
            QDialogButtonBox.StandardButton.Ok), self)
        button_box.accepted.connect(self.accept)

        layout = QFormLayout(self)

        default_temperature_text = ', '.join(
            [str(temp) for temp in transcription_options.temperature])
        self.temperature_line_edit = LineEdit(default_temperature_text, self)
        self.temperature_line_edit.setPlaceholderText(
            _('Comma-separated, e.g. "0.0, 0.2, 0.4, 0.6, 0.8, 1.0"'))
        self.temperature_line_edit.setMinimumWidth(170)
        self.temperature_line_edit.textChanged.connect(
            self.on_temperature_changed)
        self.temperature_line_edit.setValidator(TemperatureValidator(self))
        self.temperature_line_edit.setEnabled(transcription_options.model.model_type == ModelType.WHISPER)

        self.initial_prompt_text_edit = QPlainTextEdit(
            transcription_options.initial_prompt, self)
        self.initial_prompt_text_edit.textChanged.connect(
            self.on_initial_prompt_changed)
        self.initial_prompt_text_edit.setEnabled(
            transcription_options.model.model_type == ModelType.WHISPER)

        layout.addRow(_('Temperature:'), self.temperature_line_edit)
        layout.addRow(_('Initial Prompt:'), self.initial_prompt_text_edit)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.setFixedSize(self.sizeHint())

    def on_temperature_changed(self, text: str):
        try:
            temperatures = [float(temp.strip()) for temp in text.split(',')]
            self.transcription_options.temperature = tuple(temperatures)
            self.transcription_options_changed.emit(self.transcription_options)
        except ValueError:
            pass

    def on_initial_prompt_changed(self):
        self.transcription_options.initial_prompt = self.initial_prompt_text_edit.toPlainText()
        self.transcription_options_changed.emit(self.transcription_options)


class TemperatureValidator(QValidator):
    def __init__(self, parent: Optional[QObject] = ...) -> None:
        super().__init__(parent)

    def validate(self, text: str, cursor_position: int) -> Tuple['QValidator.State', str, int]:
        try:
            temp_strings = [temp.strip() for temp in text.split(',')]
            if temp_strings[-1] == '':
                return QValidator.State.Intermediate, text, cursor_position
            _ = [float(temp) for temp in temp_strings]
            return QValidator.State.Acceptable, text, cursor_position
        except ValueError:
            return QValidator.State.Invalid, text, cursor_position
