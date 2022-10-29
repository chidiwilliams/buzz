import enum
import os
import platform
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import humanize
import sounddevice
from PyQt6 import QtGui
from PyQt6.QtCore import (QDateTime, QObject, QRect, QSettings, Qt, QTimer,
                          pyqtSignal)
from PyQt6.QtGui import (QAction, QCloseEvent, QKeySequence, QPixmap,
                         QTextCursor, QIcon)
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog,
                             QGridLayout, QLabel, QMainWindow, QPlainTextEdit,
                             QProgressDialog, QPushButton, QVBoxLayout,
                             QWidget)
from whisper import tokenizer

from __version__ import VERSION

from transcriber import FileTranscriber, OutputFormat, RecordingTranscriber
from whispr import Task

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
        devices: sounddevice.DeviceList = sounddevice.query_devices()
        input_devices = filter(
            lambda device: device.get('max_input_channels') > 0, devices)
        return list(map(lambda device: (device.get('index'), device.get('name')), input_devices))

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
        self.addItems(map(lambda format: format.value.upper(), self.formats))
        self.currentIndexChanged.connect(self.on_index_changed)
        self.setCurrentText(default_format.value.title())

    def on_index_changed(self, index: int):
        self.output_format_changed.emit(self.formats[index])


class Quality(enum.Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


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

    def update_progress(self, current_size: int):
        self.setValue(current_size)

        fraction_completed = current_size / self.total_size
        if fraction_completed > 0:
            time_spent = (datetime.now() - self.start_time).total_seconds()
            time_left = (time_spent / fraction_completed) - time_spent
            self.setLabelText(
                f'Processing {self.short_file_path} ({fraction_completed:.2%}, {humanize.naturaldelta(time_left)} remaining)')


class FileTranscriberObject(QObject):
    download_model_progress = pyqtSignal(tuple)
    event_received = pyqtSignal(object)
    transcriber: FileTranscriber

    def __init__(
            self, model_name: str, use_whisper_cpp: bool, language: Optional[str],
            task: Task, file_path: str, output_file_path: str,
            output_format: OutputFormat, parent: Optional['QObject'], *args) -> None:
        super().__init__(parent, *args)
        self.transcriber = FileTranscriber(
            model_name=model_name, use_whisper_cpp=use_whisper_cpp,
            on_download_model_chunk=self.on_download_model_progress,
            language=language, task=task, file_path=file_path,
            output_file_path=output_file_path, output_format=output_format,
            event_callback=self.on_file_transcriber_event)

    def on_download_model_progress(self, current: int, total: int):
        self.download_model_progress.emit((current, total))

    def on_file_transcriber_event(self, event: FileTranscriber.Event):
        self.event_received.emit(event)

    def start(self):
        self.transcriber.start()

    def stop(self):
        self.transcriber.stop()

    def stop_loading_model(self):
        self.transcriber.stop_loading_model()


class RecordingTranscriberObject(QObject):
    """
    TranscriberWithSignal exports the text callback from a Transcriber
    as a QtSignal to allow updating the UI from a secondary thread.
    """

    event_changed = pyqtSignal(RecordingTranscriber.Event)
    download_model_progress = pyqtSignal(tuple)
    transcriber: RecordingTranscriber

    def __init__(self, model_name, use_whisper_cpp, language: Optional[str],
                 task: Task, input_device_index: Optional[int], parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.transcriber = RecordingTranscriber(
            model_name=model_name, use_whisper_cpp=use_whisper_cpp,
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

    def stop_loading_model(self):
        self.transcriber.stop_loading_model()


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
        Quality.LOW: ('tiny', 'tiny.en'),
        Quality.MEDIUM: ('base', 'base.en'),
        Quality.HIGH: ('small', 'small.en'),
    }[quality][0]


class FileTranscriberWidget(QWidget):
    selected_quality = Quality.LOW
    selected_language: Optional[str] = None
    selected_task = Task.TRANSCRIBE
    selected_output_format = OutputFormat.TXT
    model_download_progress_dialog: Optional[DownloadModelProgressDialog] = None
    transcriber_progress_dialog: Optional[TranscriberProgressDialog] = None
    file_transcriber: Optional[FileTranscriberObject] = None

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

        grid = (
            ((0, 5, FormLabel('Task:', parent=self)), (5, 7, self.tasks_combo_box)),
            ((0, 5, FormLabel('Language:', parent=self)),
             (5, 7, self.languages_combo_box)),
            ((0, 5, FormLabel('Quality:', parent=self)),
             (5, 7, self.quality_combo_box)),
            ((0, 5, FormLabel('Export As:', self)),
             (5, 7, output_formats_combo_box)),
            ((9, 3, self.run_button),)
        )

        for (row_index, row) in enumerate(grid):
            for (_, cell) in enumerate(row):
                (col_offset, col_width, widget) = cell
                layout.addWidget(widget, row_index, col_offset, 1, col_width)

        self.setLayout(layout)

    def on_quality_changed(self, quality: Quality):
        self.selected_quality = quality

    def on_language_changed(self, language: str):
        self.selected_language = None if language == '' else language

    def on_task_changed(self, task: Task):
        self.selected_task = task

    def on_output_format_changed(self, output_format: OutputFormat):
        self.selected_output_format = output_format

    def on_click_run(self):
        default_path = FileTranscriber.get_default_output_file_path(
            task=self.selected_task, input_file_path=self.file_path,
            output_format=self.selected_output_format)
        (output_file, _) = QFileDialog.getSaveFileName(
            self, 'Save File', default_path, f'Text files (*.{self.selected_output_format.value})')

        if output_file == '':
            return

        use_whisper_cpp = self.settings.enable_ggml_inference(
        ) and self.selected_language is not None

        self.run_button.setDisabled(True)
        model_name = get_model_name(self.selected_quality)

        self.file_transcriber = FileTranscriberObject(
            model_name=model_name, use_whisper_cpp=use_whisper_cpp,
            file_path=self.file_path,
            language=self.selected_language, task=self.selected_task,
            output_file_path=output_file, output_format=self.selected_output_format,
            parent=self)
        self.file_transcriber.download_model_progress.connect(
            self.on_download_model_progress)
        self.file_transcriber.event_received.connect(
            self.on_transcriber_event)

        self.file_transcriber.start()

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

    def on_transcriber_event(self, event: FileTranscriber.Event):
        if isinstance(event, FileTranscriber.LoadedModelEvent):
            self.reset_model_download()
        elif isinstance(event, FileTranscriber.ProgressEvent):
            current_size = event.current_value
            total_size = event.max_value

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

            if current_size == total_size:
                self.reset_transcription()

    def on_cancel_transcriber_progress_dialog(self):
        if self.file_transcriber is not None:
            self.file_transcriber.stop()
        self.reset_transcription()

    def reset_transcription(self):
        self.run_button.setDisabled(False)
        if self.transcriber_progress_dialog is not None:
            self.transcriber_progress_dialog = None

    def on_cancel_model_progress_dialog(self):
        if self.file_transcriber is not None:
            self.file_transcriber.stop_loading_model()
        self.reset_model_download()

    def reset_model_download(self):
        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog = None


class Settings(QSettings):
    ENABLE_GGML_INFERENCE = 'enable_ggml_inference'

    def __init__(self, parent: Optional[QWidget], *args):
        super().__init__('Buzz', 'Buzz', parent, *args)

    def enable_ggml_inference(self):
        if platform.system() == 'Windows':
            return False
        return self.value(self.ENABLE_GGML_INFERENCE, False)


class RecordingTranscriberWidget(QWidget):
    current_status = RecordButton.Status.STOPPED
    selected_quality = Quality.LOW
    selected_language: Optional[str] = None
    selected_device_id: Optional[int]
    selected_task = Task.TRANSCRIBE
    model_download_progress_dialog: Optional[DownloadModelProgressDialog] = None
    settings: Settings
    transcriber: Optional[RecordingTranscriberObject] = None

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

        use_whisper_cpp = self.settings.enable_ggml_inference(
        ) and self.selected_language != None

        model_name = get_model_name(self.selected_quality)

        self.transcriber = RecordingTranscriberObject(
            model_name=model_name, use_whisper_cpp=use_whisper_cpp,
            language=self.selected_language, task=self.selected_task,
            input_device_index=self.selected_device_id,
            parent=self
        )
        self.transcriber.event_changed.connect(
            self.on_transcriber_event_changed)
        self.transcriber.download_model_progress.connect(
            self.on_download_model_progress)

        self.transcriber.start_recording()

    def on_transcriber_event_changed(self, event: RecordingTranscriber.Event):
        if isinstance(event, RecordingTranscriber.LoadedModelEvent):
            # Clear text box placeholder because the first chunk takes a while to process
            self.text_box.setPlaceholderText('')
            self.timer_label.start_timer()
            self.record_button.setDisabled(False)
            self.reset_model_download()
        elif isinstance(event, RecordingTranscriber.TranscribedNextChunkEvent):
            text = event.text.strip()
            if len(text) > 0:
                self.text_box.moveCursor(QTextCursor.MoveOperation.End)
                self.text_box.insertPlainText(text + '\n\n')
                self.text_box.moveCursor(QTextCursor.MoveOperation.End)

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

    def stop_recording(self):
        if self.transcriber is not None:
            self.transcriber.stop_recording()
        self.timer_label.stop_timer()

    def on_cancel_model_progress_dialog(self):
        if self.transcriber is not None:
            self.transcriber.stop_loading_model()
        self.reset_model_download()
        self.record_button.force_stop()
        self.record_button.setDisabled(False)

    def reset_model_download(self):
        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog = None

class Icon(QIcon):
    def __init__(self):
        super().__init__('assets/buzz.ico')

class AboutDialog(QDialog):
    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__(parent)

        self.setFixedSize(200, 200)

        self.setWindowIcon(Icon())
        self.setWindowTitle(f'About {APP_NAME}')

        layout = QVBoxLayout(self)

        image_label = QLabel()
        pixmap = QPixmap('./assets/buzz-icon-1024.png').scaled(
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

        layout.addStretch(1)
        layout.addWidget(image_label)
        layout.addWidget(buzz_label)
        layout.addWidget(version_label)
        layout.addStretch(1)

        self.setLayout(layout)


class MainWindow(QMainWindow):
    new_import_window_triggered = pyqtSignal(tuple)

    def __init__(self, title: str, w: int, h: int, parent: Optional[QWidget], *args):
        super().__init__(parent, *args)

        self.setFixedSize(w, h)
        self.setWindowTitle(f'{title} - {APP_NAME}')
        self.setWindowIcon(Icon())

        import_audio_file_action = QAction("&Import Audio File...", self)
        import_audio_file_action.triggered.connect(
            self.on_import_audio_file_action)
        import_audio_file_action.setShortcut(QKeySequence.fromString('Ctrl+O'))

        menu = self.menuBar()

        self.file_menu = menu.addMenu("&File")
        self.file_menu.addAction(import_audio_file_action)

        self.about_action = QAction(f'&About {APP_NAME}', self)
        self.about_action.triggered.connect(self.on_trigger_about_action)

        self.help_menu = menu.addMenu("&Help")
        self.help_menu.addAction(self.about_action)

        self.settings = Settings(self)

        if platform.system() != 'Windows':
            enable_ggml_inference_action = QAction(
                '&Enable GGML Inference', self)
            enable_ggml_inference_action.setCheckable(True)
            enable_ggml_inference_action.setChecked(
                bool(self.settings.enable_ggml_inference()))
            enable_ggml_inference_action.triggered.connect(
                self.on_toggle_enable_ggml_inference)

    def on_import_audio_file_action(self):
        (file_path, _) = QFileDialog.getOpenFileName(
            self, 'Select audio file', '', 'Audio Files (*.mp3 *.wav *.m4a *.ogg);;Video Files (*.mp4 *.webm *.ogm)')
        if file_path == '':
            return
        self.new_import_window_triggered.emit((file_path, self.geometry()))

    def on_toggle_enable_ggml_inference(self, state: bool):
        self.settings.setValue(Settings.ENABLE_GGML_INFERENCE, state)

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
            file_path), w=400, h=210, parent=parent, *args)

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
