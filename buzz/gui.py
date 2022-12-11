import enum
import logging
import os
import platform
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import humanize
import sounddevice
from PyQt6 import QtGui
from PyQt6.QtCore import (QDateTime, QObject, QRect, QSettings, Qt,
                          QThreadPool, QTimer, QUrl, pyqtSignal)
from PyQt6.QtGui import (QAction, QCloseEvent, QDesktopServices, QIcon,
                         QKeySequence, QPixmap, QTextCursor)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QGridLayout, QLabel, QMainWindow,
                             QMessageBox, QPlainTextEdit, QProgressDialog,
                             QPushButton, QVBoxLayout, QWidget)
from requests import get
from whisper import tokenizer

from .__version__ import VERSION
from .model_loader import ModelLoader
from .transcriber import (LOADED_WHISPER_DLL, SUPPORTED_OUTPUT_FORMATS,
                          OutputFormat, RecordingTranscriber, Task,
                          WhisperCppFileTranscriber, WhisperFileTranscriber,
                          get_default_output_file_path)

APP_NAME = 'Buzz'


def get_platform_styles(all_platform_styles: Dict[str, str]):
    return all_platform_styles.get(platform.system(), '')


def get_short_file_path(file_path: str):
    basename = os.path.basename(file_path)
    if len(basename) > 20:
        return f'{basename[0:10]}...{basename[-5:]}'
    return basename


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

    def __init__(self, parent: Optional[QWidget] = None, *args) -> None:
        super().__init__(parent, *args)
        self.audio_devices = self.get_audio_devices()
        self.addItems(map(lambda device: device[1], self.audio_devices))
        self.currentIndexChanged.connect(self.on_index_changed)
        if self.get_default_device_id() != -1:
            default_device_index = next(i for i, device in enumerate(
                self.audio_devices) if device[0] == self.get_default_device_id())
            self.setCurrentIndex(default_device_index)

    def get_audio_devices(self) -> List[Tuple[int, str]]:
        try:
            devices: sounddevice.DeviceList = sounddevice.query_devices()
            input_devices = filter(
                lambda device: device.get('max_input_channels') > 0, devices)
            return list(map(lambda device: (device.get('index'), device.get('name')), input_devices))
        except UnicodeDecodeError:
            QMessageBox.critical(
                self, '', 'An error occured while loading your audio devices. Please check the application logs for more information.')
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
    # language is a languge key from whisper.tokenizer.LANGUAGES or '' for "detect langugage"
    languageChanged = pyqtSignal(str)

    def __init__(self, default_language: Optional[str], parent: Optional[QWidget] = None, *args) -> None:
        super().__init__(parent, *args)

        whisper_languages = sorted(
            [(lang, tokenizer.LANGUAGES[lang].title()) for lang in tokenizer.LANGUAGES], key=lambda lang: lang[1])
        self.languages = [('', 'Detect Language')] + whisper_languages

        self.addItems([lang[1] for lang in self.languages])
        self.currentIndexChanged.connect(self.on_index_changed)

        default_language_key = default_language if default_language != '' else None
        default_language_index = next((i for i, lang in enumerate(self.languages)
                                       if lang[0] == default_language_key), 0)
        self.setCurrentIndex(default_language_index)

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


class OutputFormatsComboBox(QComboBox):
    output_format_changed = pyqtSignal(OutputFormat)
    formats: List[OutputFormat]

    def __init__(self, default_format: OutputFormat, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.formats = [i for i in OutputFormat]
        self.addItems(
            map(lambda format: f'.{format.value.lower()}', self.formats))
        self.currentIndexChanged.connect(self.on_index_changed)
        self.setCurrentText(default_format.value.title())

    def on_index_changed(self, index: int):
        self.output_format_changed.emit(self.formats[index])


class Quality(enum.Enum):
    VERY_LOW = 'very low'
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    VERY_HIGH = 'very high'


class QualityComboBox(QComboBox):
    quality_changed = pyqtSignal(Quality)

    def __init__(self, default_quality: Quality, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.qualities = [i for i in Quality]
        self.addItems(
            map(lambda quality: quality.value.title(), self.qualities))
        self.currentIndexChanged.connect(self.on_index_changed)
        self.setCurrentText(default_quality.value.title())

    def on_index_changed(self, index: int):
        self.quality_changed.emit(self.qualities[index])


class TextDisplayBox(QPlainTextEdit):
    """TextDisplayBox is a read-only textbox"""

    os_styles = {
        'Darwin': '''QTextEdit {
            border: 0;
        }'''
    }

    def __init__(self, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.setReadOnly(True)
        self.setPlaceholderText('Click Record to begin...')
        self.setStyleSheet(
            '''QTextEdit {
                } %s''' % get_platform_styles(self.os_styles))


class RecordButton(QPushButton):
    class Status(enum.Enum):
        RECORDING = enum.auto()
        STOPPED = enum.auto()

    current_status = Status.STOPPED
    status_changed = pyqtSignal(Status)

    def __init__(self, parent: Optional[QWidget], *args) -> None:
        super().__init__("Record", parent, *args)
        self.clicked.connect(self.on_click_record)
        self.status_changed.connect(self.on_status_changed)
        self.setDefault(True)

    def on_click_record(self):
        current_status: RecordButton.Status
        if self.current_status == self.Status.RECORDING:
            current_status = self.Status.STOPPED
        else:
            current_status = self.Status.RECORDING

        self.status_changed.emit(current_status)

    def on_status_changed(self, status: Status):
        self.current_status = status
        if status == self.Status.RECORDING:
            self.setText('Stop')
            self.setDefault(False)
        else:
            self.setText('Record')
            self.setDefault(True)

    def force_stop(self):
        self.on_status_changed(self.Status.STOPPED)


class DownloadModelProgressDialog(QProgressDialog):
    start_time: datetime

    def __init__(self, total_size: int, parent: Optional[QWidget], *args) -> None:
        super().__init__('Downloading resources (0%, unknown time remaining)',
                         'Cancel', 0, total_size, parent, *args)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.start_time = datetime.now()

    def setValue(self, current_size: int) -> None:
        super().setValue(current_size)

        fraction_completed = current_size / self.maximum()
        if fraction_completed > 0:
            time_spent = (datetime.now() - self.start_time).total_seconds()
            time_left = (time_spent / fraction_completed) - time_spent

            self.setLabelText(
                f'Downloading resources ({(current_size / self.maximum()):.2%}, {humanize.naturaldelta(time_left)} remaining)')


class TranscriberProgressDialog(QProgressDialog):
    short_file_path: str
    start_time: datetime
    is_canceled = False

    def __init__(self, file_path: str, total_size: int, parent: Optional[QWidget], *args) -> None:
        short_file_path = get_short_file_path(file_path)
        label = f'Processing {short_file_path} (0%, unknown time remaining)'
        super().__init__(label, 'Cancel', 0, total_size, parent, *args)

        self.total_size = total_size
        self.short_file_path = short_file_path
        self.start_time = datetime.now()

        # Open dialog immediately
        self.setMinimumDuration(0)

        self.setValue(0)
        self.setWindowModality(Qt.WindowModality.WindowModal)

    def update_progress(self, current_size: int):
        self.setValue(current_size)

        fraction_completed = current_size / self.total_size
        if fraction_completed > 0:
            time_spent = (datetime.now() - self.start_time).total_seconds()
            time_left = (time_spent / fraction_completed) - time_spent
            self.setLabelText(
                f'Processing {self.short_file_path} ({fraction_completed:.2%}, {humanize.naturaldelta(time_left)} remaining)')


class RecordingTranscriberObject(QObject):
    """
    TranscriberWithSignal exports the text callback from a Transcriber
    as a QtSignal to allow updating the UI from a secondary thread.
    """

    event_changed = pyqtSignal(RecordingTranscriber.Event)
    download_model_progress = pyqtSignal(tuple)
    transcriber: RecordingTranscriber

    def __init__(self, model_path: str, use_whisper_cpp, language: Optional[str],
                 task: Task, input_device_index: Optional[int], parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.transcriber = RecordingTranscriber(
            model_path=model_path, use_whisper_cpp=use_whisper_cpp,
            on_download_model_chunk=self.on_download_model_progress, language=language,
            event_callback=self.event_callback, task=task,
            input_device_index=input_device_index)

    def start_recording(self):
        self.transcriber.start_recording()

    def event_callback(self, event: RecordingTranscriber.Event):
        self.event_changed.emit(event)

    def on_download_model_progress(self, current: int, total: int):
        self.download_model_progress.emit((current, total))

    def stop_recording(self):
        self.transcriber.stop_recording()


class TimerLabel(QLabel):
    start_time: Optional[QDateTime]

    def __init__(self, parent: Optional[QWidget]):
        super().__init__(parent)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_next_interval)
        self.on_next_interval(stopped=True)
        self.setAlignment(Qt.AlignmentFlag(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight))

    def start_timer(self):
        self.timer.start(1000)
        self.start_time = QDateTime.currentDateTimeUtc()
        self.on_next_interval()

    def stop_timer(self):
        self.timer.stop()
        self.on_next_interval(stopped=True)

    def on_next_interval(self, stopped=False):
        if stopped:
            self.setText('--:--')
        elif self.start_time != None:
            seconds_passed = self.start_time.secsTo(
                QDateTime.currentDateTimeUtc())
            self.setText('{0:02}:{1:02}'.format(
                seconds_passed // 60, seconds_passed % 60))


def get_model_name(quality: Quality) -> str:
    return {
        Quality.VERY_LOW:  'tiny',
        Quality.LOW:       'base',
        Quality.MEDIUM:    'small',
        Quality.HIGH:      'medium',
        Quality.VERY_HIGH: 'large',
    }[quality]


def show_model_download_error_dialog(parent: QWidget, error: str):
    message = f'Unable to load the Whisper model: {error}. Please retry or check the application logs for more information.'
    QMessageBox.critical(parent, '', message)


class FileTranscriberWidget(QWidget):
    selected_quality = Quality.VERY_LOW
    selected_language: Optional[str] = None
    selected_task = Task.TRANSCRIBE
    selected_output_format = OutputFormat.TXT
    enabled_word_level_timings = False
    model_download_progress_dialog: Optional[DownloadModelProgressDialog] = None
    transcriber_progress_dialog: Optional[TranscriberProgressDialog] = None
    file_transcriber: Optional[Union[WhisperFileTranscriber,
                                     WhisperCppFileTranscriber]] = None
    model_loader: Optional[ModelLoader] = None
    transcribed = pyqtSignal()

    def __init__(self, file_path: str, parent: Optional[QWidget]) -> None:
        super().__init__(parent)

        layout = QGridLayout(self)

        self.settings = Settings(self)

        self.file_path = file_path

        self.quality_combo_box = QualityComboBox(
            default_quality=self.selected_quality,
            parent=self)
        self.quality_combo_box.quality_changed.connect(self.on_quality_changed)

        self.languages_combo_box = LanguagesComboBox(
            default_language=self.selected_language,
            parent=self)
        self.languages_combo_box.languageChanged.connect(
            self.on_language_changed)

        self.tasks_combo_box = TasksComboBox(
            default_task=self.selected_task,
            parent=self)
        self.tasks_combo_box.taskChanged.connect(self.on_task_changed)

        self.run_button = QPushButton('Run', self)
        self.run_button.clicked.connect(self.on_click_run)
        self.run_button.setDefault(True)

        output_formats_combo_box = OutputFormatsComboBox(
            default_format=self.selected_output_format, parent=self)
        output_formats_combo_box.output_format_changed.connect(
            self.on_output_format_changed)

        self.word_level_timings_checkbox = QCheckBox('Word-level timings')
        self.word_level_timings_checkbox.stateChanged.connect(
            self.on_word_level_timings_changed)
        self.word_level_timings_checkbox.setDisabled(True)

        grid = (
            ((0, 5, FormLabel('Task:', parent=self)), (5, 7, self.tasks_combo_box)),
            ((0, 5, FormLabel('Language:', parent=self)),
             (5, 7, self.languages_combo_box)),
            ((0, 5, FormLabel('Quality:', parent=self)),
             (5, 7, self.quality_combo_box)),
            ((0, 5, FormLabel('Export As:', self)),
             (5, 7, output_formats_combo_box)),
            ((5, 7, self.word_level_timings_checkbox),),
            ((9, 3, self.run_button),)
        )

        for (row_index, row) in enumerate(grid):
            for (_, cell) in enumerate(row):
                (col_offset, col_width, widget) = cell
                layout.addWidget(widget, row_index, col_offset, 1, col_width)

        self.setLayout(layout)
        self.pool = QThreadPool()

    def on_quality_changed(self, quality: Quality):
        self.selected_quality = quality

    def on_language_changed(self, language: str):
        self.selected_language = None if language == '' else language

    def on_task_changed(self, task: Task):
        self.selected_task = task

    def on_output_format_changed(self, output_format: OutputFormat):
        self.selected_output_format = output_format
        self.word_level_timings_checkbox.setDisabled(
            output_format == OutputFormat.TXT)

    def on_click_run(self):
        default_path = get_default_output_file_path(
            task=self.selected_task, input_file_path=self.file_path,
            output_format=self.selected_output_format)
        (output_file, _) = QFileDialog.getSaveFileName(
            self, 'Save File', default_path, f'Text files (*.{self.selected_output_format.value})')

        if output_file == '':
            return

        use_whisper_cpp = self.settings.get_enable_ggml_inference(
        ) and self.selected_language is not None

        self.run_button.setDisabled(True)
        model_name = get_model_name(self.selected_quality)

        def start_file_transcription(model_path: str):
            if self.model_download_progress_dialog is not None:
                self.model_download_progress_dialog = None

            if use_whisper_cpp:
                self.file_transcriber = WhisperCppFileTranscriber(
                    model_path=model_path, file_path=self.file_path,
                    language=self.selected_language, task=self.selected_task,
                    output_file_path=output_file, output_format=self.selected_output_format,
                    word_level_timings=self.enabled_word_level_timings,
                )
            else:
                self.file_transcriber = WhisperFileTranscriber(
                    model_path=model_path, file_path=self.file_path,
                    language=self.selected_language, task=self.selected_task,
                    output_file_path=output_file, output_format=self.selected_output_format,
                    word_level_timings=self.enabled_word_level_timings,
                )

            self.file_transcriber.signals.progress.connect(
                self.on_transcriber_progress)
            self.file_transcriber.signals.completed.connect(
                self.on_transcriber_complete)
            self.pool.start(self.file_transcriber)

        self.model_loader = ModelLoader(
            name=model_name, use_whisper_cpp=use_whisper_cpp)
        self.model_loader.signals.progress.connect(
            self.on_download_model_progress)
        self.model_loader.signals.completed.connect(start_file_transcription)
        self.model_loader.signals.error.connect(self.on_download_model_error)

        self.pool.start(self.model_loader)

    def on_download_model_progress(self, progress: Tuple[int, int]):
        (current_size, total_size) = progress

        if self.model_download_progress_dialog is None:
            self.model_download_progress_dialog = DownloadModelProgressDialog(
                total_size=total_size, parent=self)
            self.model_download_progress_dialog.canceled.connect(
                self.on_cancel_model_progress_dialog)

        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.setValue(
                current_size=current_size)

    def on_download_model_error(self, error: str):
        show_model_download_error_dialog(self, error)
        self.reset_transcription()

    def on_transcriber_progress(self, progress: Tuple[int, int]):
        (current_size, total_size) = progress

        # Create a dialog
        if self.transcriber_progress_dialog is None:
            self.transcriber_progress_dialog = TranscriberProgressDialog(
                file_path=self.file_path, total_size=total_size, parent=self)
            self.transcriber_progress_dialog.canceled.connect(
                self.on_cancel_transcriber_progress_dialog)

        # Update the progress of the dialog unless it has
        # been canceled before this progress update arrived
        if self.transcriber_progress_dialog is not None:
            self.transcriber_progress_dialog.update_progress(current_size)

    def on_transcriber_complete(self):
        self.reset_transcription()
        self.transcribed.emit()

    def on_cancel_transcriber_progress_dialog(self):
        if self.file_transcriber is not None:
            self.file_transcriber.stop()
        self.reset_transcription()

    def reset_transcription(self):
        self.run_button.setDisabled(False)
        if self.transcriber_progress_dialog is not None:
            self.transcriber_progress_dialog.close()
            self.transcriber_progress_dialog = None

    def on_cancel_model_progress_dialog(self):
        if self.model_loader is not None:
            self.model_loader.stop()
        self.reset_model_download()

    def reset_model_download(self):
        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog = None

    def on_word_level_timings_changed(self, value: int):
        self.enabled_word_level_timings = value == Qt.CheckState.Checked.value


class Settings(QSettings):
    _ENABLE_GGML_INFERENCE = 'enable_ggml_inference'

    def __init__(self, parent: Optional[QWidget] = None, *args):
        super().__init__('Buzz', 'Buzz', parent, *args)
        logging.debug('Loaded settings from path = %s', self.fileName())

    def get_enable_ggml_inference(self) -> bool:
        if LOADED_WHISPER_DLL is False:
            return False
        return self._value_to_bool(self.value(self._ENABLE_GGML_INFERENCE, False))

    def set_enable_ggml_inference(self, value: bool) -> None:
        self.setValue(self._ENABLE_GGML_INFERENCE, value)

    # Convert QSettings value to boolean: https://forum.qt.io/topic/108622/how-to-get-a-boolean-value-from-qsettings-correctly
    @staticmethod
    def _value_to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.lower() == 'true'

        return bool(value)


class RecordingTranscriberWidget(QWidget):
    current_status = RecordButton.Status.STOPPED
    selected_quality = Quality.VERY_LOW
    selected_language: Optional[str] = None
    selected_device_id: Optional[int]
    selected_task = Task.TRANSCRIBE
    model_download_progress_dialog: Optional[DownloadModelProgressDialog] = None
    settings: Settings
    transcriber: Optional[RecordingTranscriberObject] = None
    model_loader: Optional[ModelLoader] = None

    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__(parent)

        layout = QGridLayout(self)

        self.settings = Settings(self)

        self.quality_combo_box = QualityComboBox(
            default_quality=self.selected_quality,
            parent=self)
        self.quality_combo_box.quality_changed.connect(self.on_quality_changed)

        self.languages_combo_box = LanguagesComboBox(
            default_language=self.selected_language,
            parent=self)
        self.languages_combo_box.languageChanged.connect(
            self.on_language_changed)

        self.audio_devices_combo_box = AudioDevicesComboBox(self)
        self.audio_devices_combo_box.device_changed.connect(
            self.on_device_changed)
        self.selected_device_id = self.audio_devices_combo_box.get_default_device_id()

        self.tasks_combo_box = TasksComboBox(
            default_task=Task.TRANSCRIBE,
            parent=self)
        self.tasks_combo_box.taskChanged.connect(self.on_task_changed)

        self.timer_label = TimerLabel(self)

        self.record_button = RecordButton(self)
        self.record_button.status_changed.connect(self.on_status_changed)

        self.text_box = TextDisplayBox(self)

        grid = (
            ((0, 5, FormLabel('Task:', self)), (5, 7, self.tasks_combo_box)),
            ((0, 5, FormLabel('Language:', self)),
             (5, 7, self.languages_combo_box)),
            ((0, 5, FormLabel('Quality:', self)), (5, 7, self.quality_combo_box)),
            ((0, 5, FormLabel('Microphone:', self)),
             (5, 7, self.audio_devices_combo_box)),
            ((6, 3, self.timer_label), (9, 3, self.record_button)),
            ((0, 12, self.text_box),),
        )

        for (row_index, row) in enumerate(grid):
            for (_, cell) in enumerate(row):
                (col_offset, col_width, widget) = cell
                layout.addWidget(widget, row_index, col_offset, 1, col_width)

        self.setLayout(layout)

        self.pool = QThreadPool()

    def on_device_changed(self, device_id: int):
        self.selected_device_id = device_id

    def on_status_changed(self, status: RecordButton.Status):
        if status == RecordButton.Status.RECORDING:
            self.start_recording()
        else:
            self.stop_recording()

    def on_quality_changed(self, quality: Quality):
        self.selected_quality = quality

    def on_language_changed(self, language: str):
        self.selected_language = None if language == '' else language

    def on_task_changed(self, task: Task):
        self.selected_task = task

    def start_recording(self):
        self.record_button.setDisabled(True)

        use_whisper_cpp = self.settings.get_enable_ggml_inference(
        ) and self.selected_language is not None

        model_name = get_model_name(self.selected_quality)

        def start_recording_transcription(model_path: str):
            # Clear text box placeholder because the first chunk takes a while to process
            self.text_box.setPlaceholderText('')
            self.timer_label.start_timer()
            self.record_button.setDisabled(False)
            if self.model_download_progress_dialog is not None:
                self.model_download_progress_dialog = None

            self.transcriber = RecordingTranscriberObject(
                model_path=model_path, use_whisper_cpp=use_whisper_cpp,
                language=self.selected_language, task=self.selected_task,
                input_device_index=self.selected_device_id,
                parent=self
            )
            self.transcriber.event_changed.connect(
                self.on_transcriber_event_changed)
            self.transcriber.download_model_progress.connect(
                self.on_download_model_progress)

            self.transcriber.start_recording()

        self.model_loader = ModelLoader(
            name=model_name, use_whisper_cpp=use_whisper_cpp)
        self.model_loader.signals.progress.connect(
            self.on_download_model_progress)
        self.model_loader.signals.completed.connect(
            start_recording_transcription)
        self.model_loader.signals.error.connect(self.on_download_model_error)

        self.pool.start(self.model_loader)

    def on_download_model_progress(self, progress: Tuple[int, int]):
        (current_size, _) = progress

        if self.model_download_progress_dialog is None:
            self.model_download_progress_dialog = DownloadModelProgressDialog(
                total_size=100, parent=self)
            self.model_download_progress_dialog.canceled.connect(
                self.on_cancel_model_progress_dialog)

        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.setValue(
                current_size=current_size)

    def on_download_model_error(self, error: str):
        show_model_download_error_dialog(self, error)
        self.stop_recording()
        self.record_button.force_stop()
        self.record_button.setDisabled(False)

    def on_transcriber_event_changed(self, event: RecordingTranscriber.Event):
        if isinstance(event, RecordingTranscriber.TranscribedNextChunkEvent):
            text = event.text.strip()
            if len(text) > 0:
                self.text_box.moveCursor(QTextCursor.MoveOperation.End)
                self.text_box.insertPlainText(text + '\n\n')
                self.text_box.moveCursor(QTextCursor.MoveOperation.End)

    def stop_recording(self):
        if self.transcriber is not None:
            self.transcriber.stop_recording()
        self.timer_label.stop_timer()

    def on_cancel_model_progress_dialog(self):
        if self.model_loader is not None:
            self.model_loader.stop()
        self.reset_model_download()
        self.record_button.force_stop()
        self.record_button.setDisabled(False)

    def reset_model_download(self):
        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog = None


ICON_PATH = 'assets/buzz.ico'
ICON_LARGE_PATH = 'assets/buzz-icon-1024.png'


def get_asset_path(path: str):
    base_dir = os.path.dirname(sys.executable if getattr(
        sys, 'frozen', False) else __file__)
    return os.path.join(base_dir, path)


class AppIcon(QIcon):
    def __init__(self):
        super().__init__(get_asset_path(ICON_PATH))


class AboutDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setFixedSize(200, 200)

        self.setWindowIcon(AppIcon())
        self.setWindowTitle(f'About {APP_NAME}')

        layout = QVBoxLayout(self)

        image_label = QLabel()
        pixmap = QPixmap(get_asset_path(ICON_LARGE_PATH)).scaled(
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

        version_label = QLabel(f'Version {VERSION}')
        version_label.setAlignment(Qt.AlignmentFlag(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter))

        check_updates_button = QPushButton('Check for updates')
        check_updates_button.clicked.connect(self.on_click_check_for_updates)

        layout.addStretch(1)
        layout.addWidget(image_label)
        layout.addWidget(buzz_label)
        layout.addWidget(version_label)
        layout.addWidget(check_updates_button)
        layout.addStretch(1)

        self.setLayout(layout)

    def on_click_check_for_updates(self):
        response = get(
            'https://api.github.com/repos/chidiwilliams/buzz/releases/latest', timeout=15).json()
        version_number = response.get('name')
        if version_number == 'v' + VERSION:
            dialog = QMessageBox(self)
            dialog.setText("You're up to date!")
            dialog.exec()
        else:
            QDesktopServices.openUrl(
                QUrl('https://github.com/chidiwilliams/buzz/releases/latest'))


class MainWindow(QMainWindow):
    new_import_window_triggered = pyqtSignal(tuple)

    def __init__(self, title: str, w: int, h: int, parent: Optional[QWidget], *args):
        super().__init__(parent, *args)

        self.setFixedSize(w, h)
        self.setWindowTitle(f'{title} - {APP_NAME}')
        self.setWindowIcon(AppIcon())

        import_audio_file_action = QAction("&Import Audio File...", self)
        import_audio_file_action.triggered.connect(
            self.on_import_audio_file_action)
        import_audio_file_action.setShortcut(QKeySequence.fromString('Ctrl+O'))

        menu = self.menuBar()

        self.file_menu = menu.addMenu("&File")
        self.file_menu.addAction(import_audio_file_action)

        self.about_action = QAction(f'&About {APP_NAME}', self)
        self.about_action.triggered.connect(self.on_trigger_about_action)

        self.settings = Settings(self)

        enable_ggml_inference_action = QAction(
            '&Enable GGML Inference', self)
        enable_ggml_inference_action.setCheckable(True)
        enable_ggml_inference_action.setChecked(
            bool(self.settings.get_enable_ggml_inference()))
        enable_ggml_inference_action.triggered.connect(
            self.on_toggle_enable_ggml_inference)
        enable_ggml_inference_action.setDisabled(LOADED_WHISPER_DLL is False)

        settings_menu = menu.addMenu("&Settings")
        settings_menu.addAction(enable_ggml_inference_action)

        self.help_menu = menu.addMenu("&Help")
        self.help_menu.addAction(self.about_action)

    def on_import_audio_file_action(self):
        (file_path, _) = QFileDialog.getOpenFileName(
            self, 'Select audio file', '', SUPPORTED_OUTPUT_FORMATS)
        if file_path == '':
            return
        self.new_import_window_triggered.emit((file_path, self.geometry()))

    def on_toggle_enable_ggml_inference(self, state: bool):
        self.settings.set_enable_ggml_inference(state)

    def on_trigger_about_action(self):
        about_dialog = AboutDialog(self)
        about_dialog.exec()


class RecordingTranscriberMainWindow(MainWindow):
    def __init__(self, parent: Optional[QWidget], *args) -> None:
        super().__init__(title='Live Recording', w=400, h=500, parent=parent, *args)

        self.central_widget = RecordingTranscriberWidget(self)
        self.central_widget.setContentsMargins(10, 10, 10, 10)
        self.setCentralWidget(self.central_widget)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.central_widget.stop_recording()
        return super().closeEvent(event)


class FileTranscriberMainWindow(MainWindow):
    central_widget: FileTranscriberWidget

    def __init__(self, file_path: str, parent: Optional[QWidget], *args) -> None:
        super().__init__(title=get_short_file_path(
            file_path), w=400, h=240, parent=parent, *args)

        self.central_widget = FileTranscriberWidget(file_path, self)
        self.central_widget.setContentsMargins(10, 10, 10, 10)
        self.setCentralWidget(self.central_widget)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.central_widget.on_cancel_transcriber_progress_dialog()
        return super().closeEvent(event)


class Application(QApplication):
    windows: List[MainWindow] = []

    def __init__(self) -> None:
        super().__init__(sys.argv)

        window = RecordingTranscriberMainWindow(None)
        window.new_import_window_triggered.connect(self.open_import_window)
        window.show()

        self.windows.append(window)

    def open_import_window(self, window_config: Tuple[str, QRect]):
        (file_path, geometry) = window_config

        window = FileTranscriberMainWindow(file_path, None)

        # Set window to open at an offset from the calling sibling
        OFFSET = 35
        geometry = QRect(geometry.left() + OFFSET, geometry.top() + OFFSET,
                         geometry.width(), geometry.height())
        window.setGeometry(geometry)
        self.windows.append(window)

        window.new_import_window_triggered.connect(self.open_import_window)
        window.show()
