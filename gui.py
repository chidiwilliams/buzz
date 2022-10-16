import enum
import logging
import os
import platform
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import humanize
import sounddevice
import whisper
from PyQt6.QtCore import QDateTime, QObject, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QTextCursor
from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QGridLayout,
                             QLabel, QMainWindow, QPlainTextEdit,
                             QProgressDialog, QPushButton, QWidget)
from whisper import tokenizer

import _whisper
from transcriber import (FileTranscriber, RecordingTranscriber, State, Status,
                         Task)


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

    def __init__(self, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.audio_devices = self.get_audio_devices()
        self.addItems(map(lambda device: device[1], self.audio_devices))
        self.currentIndexChanged.connect(self.on_index_changed)
        if self.get_default_device_id() != -1 and len(self.audio_devices) > 0:
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
        return sounddevice.default.device[0]


class LanguagesComboBox(QComboBox):
    """LanguagesComboBox displays a list of languages available to use with Whisper"""
    # language is a languge key from whisper.tokenizer.LANGUAGES or '' for "detect langugage"
    languageChanged = pyqtSignal(str)

    def __init__(self, default_language: Optional[str], parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)

        whisper_languages = sorted(
            [(lang, tokenizer.LANGUAGES[lang].title())
             for lang in tokenizer.LANGUAGES.keys()],
            key=lambda lang: lang[1])
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


class DelaysComboBox(QComboBox):
    """DelaysComboBox displays the list of available delays"""
    delay_changed = pyqtSignal(int)

    def __init__(self, default_delay: int, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.delays = [5, 10, 20, 30]
        self.addItems(map(self.label, self.delays))
        self.currentIndexChanged.connect(self.on_index_changed)
        self.setCurrentText(self.label(default_delay))

    def on_index_changed(self, index: int):
        self.delay_changed.emit(self.delays[index])

    def label(self, delay: int):
        return "%ds" % delay


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


class TranscriberWithSignal(QObject):
    """
    TranscriberWithSignal exports the text callback from a Transcriber
    as a QtSignal to allow updating the UI from a secondary thread.
    """

    status_changed = pyqtSignal(Status)

    def __init__(self, model: whisper.Whisper, language: Optional[str], task: Task, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.transcriber = RecordingTranscriber(
            model=model, language=language,
            status_callback=self.on_next_status, task=task)

    def start_recording(self, input_device_index: Optional[int], block_duration: int):
        self.transcriber.start_recording(
            input_device_index=input_device_index,
            block_duration=block_duration,
        )

    def on_next_status(self, status: Status):
        self.status_changed.emit(status)

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


def get_model_name(quality: Quality, language: Optional[str]) -> str:
    return {
        Quality.LOW: ('tiny', 'tiny.en'),
        Quality.MEDIUM: ('base', 'base.en'),
        Quality.HIGH: ('small', 'small.en'),
    }[quality][1 if language == 'en' else 0]


class FileTranscriberWidget(QWidget):
    selected_quality = Quality.LOW
    selected_language: Optional[str] = None
    selected_task = Task.TRANSCRIBE
    model_download_progress_dialog: Optional[DownloadModelProgressDialog] = None
    transcriber_progress_dialog: Optional[TranscriberProgressDialog] = None
    transcribe_progress = pyqtSignal(tuple)

    def __init__(self, file_path: str, parent: Optional[QWidget]) -> None:
        super().__init__(parent)

        layout = QGridLayout(self)

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
            default_task=Task.TRANSCRIBE,
            parent=self)
        self.tasks_combo_box.taskChanged.connect(self.on_task_changed)

        self.run_button = QPushButton('Run', self)
        self.run_button.clicked.connect(self.on_click_run)
        self.run_button.setDefault(True)

        grid = (
            ((0, 5, FormLabel('Task:', parent=self)), (5, 7, self.tasks_combo_box)),
            ((0, 5, FormLabel('Language:', parent=self)),
             (5, 7, self.languages_combo_box)),
            ((0, 5, FormLabel('Quality:', parent=self)),
             (5, 7, self.quality_combo_box)),
            ((9, 3, self.run_button),)
        )

        for (row_index, row) in enumerate(grid):
            for (_, cell) in enumerate(row):
                (col_offset, col_width, widget) = cell
                layout.addWidget(widget, row_index, col_offset, 1, col_width)

        self.setLayout(layout)

        self.transcribe_progress.connect(self.handle_transcribe_progress)

    def on_quality_changed(self, quality: Quality):
        self.selected_quality = quality

    def on_language_changed(self, language: str):
        self.selected_language = None if language == '' else language

    def on_task_changed(self, task: Task):
        self.selected_task = task

    def on_click_run(self):
        default_path = FileTranscriber.get_default_output_file_path(
            task=self.selected_task, input_file_path=self.file_path)
        (output_file, _) = QFileDialog.getSaveFileName(
            self, 'Save File', default_path, 'Text files (*.txt)')

        if output_file == '':
            return

        self.run_button.setDisabled(True)
        model_name = get_model_name(
            self.selected_quality, self.selected_language)
        logging.debug(f'Loading model: {model_name}')

        self.model_loader = _whisper.ModelLoader(
            name=model_name, on_download_model_chunk=self.on_download_model_progress)

        try:
            model = self.model_loader.load()
        except _whisper.Stopped:
            self.run_button.setDisabled(False)
            return

        self.file_transcriber = FileTranscriber(
            model=model, file_path=self.file_path,
            language=self.selected_language, task=self.selected_task,
            output_file_path=output_file, progress_callback=self.on_transcribe_model_progress)
        self.file_transcriber.start()

    def on_download_model_progress(self, current_size: int, total_size: int):
        if current_size == total_size:
            self.end_download_model()
            return

        if self.model_download_progress_dialog == None:
            self.model_download_progress_dialog = DownloadModelProgressDialog(
                total_size=total_size, parent=self)
            self.model_download_progress_dialog.canceled.connect(
                self.on_cancel_model_progress_dialog)
        else:
            self.model_download_progress_dialog.setValue(current_size)

    def on_transcribe_model_progress(self, current_size: int, total_size: int):
        self.transcribe_progress.emit((current_size, total_size))

    def handle_transcribe_progress(self, progress: Tuple[int, int]):
        (current_size, total_size) = progress

        if current_size == total_size:
            self.end_transcription()
            return

        # In the middle of transcription...

        # Create a dialog if one does not exist
        if current_size == 0 and self.transcriber_progress_dialog == None:
            self.transcriber_progress_dialog = TranscriberProgressDialog(
                file_path=self.file_path, total_size=total_size, parent=self)
            self.transcriber_progress_dialog.canceled.connect(
                self.on_cancel_transcriber_progress_dialog)

        # Update the progress of the dialog unless it has
        # been canceled before this progress update arrived
        if self.transcriber_progress_dialog != None and self.transcriber_progress_dialog.wasCanceled() == False:
            self.transcriber_progress_dialog.update_progress(current_size)

    def on_cancel_transcriber_progress_dialog(self):
        self.file_transcriber.stop()
        self.end_transcription()

    def end_transcription(self):
        self.run_button.setDisabled(False)
        if self.transcriber_progress_dialog != None:
            self.transcriber_progress_dialog.destroy()
            self.transcriber_progress_dialog = None

    def on_cancel_model_progress_dialog(self):
        self.model_loader.stop()
        self.end_download_model()

    def end_download_model(self):
        if self.model_download_progress_dialog != None:
            self.model_download_progress_dialog.destroy()
            self.model_download_progress_dialog = None


class RecordingTranscriberWidget(QWidget):
    current_status = RecordButton.Status.STOPPED
    selected_quality = Quality.LOW
    selected_language: Optional[str] = None
    selected_device_id: Optional[int]
    selected_delay = 10
    selected_task = Task.TRANSCRIBE
    model_download_progress_dialog: Optional[DownloadModelProgressDialog] = None

    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__(parent)

        layout = QGridLayout(self)

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

        delays_combo_box = DelaysComboBox(
            default_delay=self.selected_delay, parent=self)
        delays_combo_box.delay_changed.connect(self.on_delay_changed)

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
            ((0, 5, FormLabel('Delay:', self)), (5, 7, delays_combo_box)),
            ((6, 3, self.timer_label), (9, 3, self.record_button)),
            ((0, 12, self.text_box),),
        )

        for (row_index, row) in enumerate(grid):
            for (_, cell) in enumerate(row):
                (col_offset, col_width, widget) = cell
                layout.addWidget(widget, row_index, col_offset, 1, col_width)

        self.setLayout(layout)

    def on_transcriber_status_changed(self, status: Status):
        if status.state == State.FINISHED_CURRENT_TRANSCRIPTION:
            text = status.text.strip()
            if len(text) > 0:
                self.text_box.moveCursor(QTextCursor.MoveOperation.End)
                self.text_box.insertPlainText(text + '\n\n')
                self.text_box.moveCursor(QTextCursor.MoveOperation.End)
        elif status.state == State.STARTING_NEXT_TRANSCRIPTION:
            pass

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

    def on_delay_changed(self, delay: int):
        self.selected_delay = delay

    def start_recording(self):
        self.record_button.setDisabled(True)

        model_name = get_model_name(
            self.selected_quality, self.selected_language)
        logging.debug(f'Loading model: {model_name}')

        self.model_loader = _whisper.ModelLoader(
            name=model_name, on_download_model_chunk=self.on_download_model_progress)

        try:
            model = self.model_loader.load()
        except _whisper.Stopped:
            self.record_button.setDisabled(False)
            self.record_button.force_stop()
            return

        self.record_button.setDisabled(False)

        # Clear text box placeholder because the first chunk takes a while to process
        self.text_box.setPlaceholderText('')
        self.timer_label.start_timer()

        self.transcriber = TranscriberWithSignal(
            model=model,
            language=self.selected_language,
            task=self.selected_task,
            parent=self
        )
        self.transcriber.status_changed.connect(
            self.on_transcriber_status_changed)
        self.transcriber.start_recording(
            input_device_index=self.selected_device_id,
            block_duration=self.selected_delay,
        )

    def on_download_model_progress(self, current_size: int, total_size: int):
        if current_size == total_size:
            self.end_download_model()
            return

        if self.model_download_progress_dialog == None:
            self.model_download_progress_dialog = DownloadModelProgressDialog(
                total_size=total_size, parent=self)
            self.model_download_progress_dialog.canceled.connect(
                self.on_cancel_model_progress_dialog)
        else:
            self.model_download_progress_dialog.setValue(current_size)

    def stop_recording(self):
        self.transcriber.stop_recording()
        self.timer_label.stop_timer()

    def on_cancel_model_progress_dialog(self):
        self.model_loader.stop()
        self.end_download_model()

    def end_download_model(self):
        if self.model_download_progress_dialog != None:
            self.model_download_progress_dialog.destroy()
            self.model_download_progress_dialog = None


class MainWindow(QMainWindow):
    new_import_window_triggered = pyqtSignal(tuple)

    def __init__(self, title: str, w: int, h: int, parent: Optional[QWidget], *args):
        super().__init__(parent, *args)

        self.setFixedSize(w, h)
        self.setWindowTitle(f'{title} — Buzz')

        import_audio_file_action = QAction("&Import Audio File...", self)
        import_audio_file_action.triggered.connect(
            self.on_import_audio_file_action)
        import_audio_file_action.setShortcut(QKeySequence.fromString('Ctrl+O'))

        menu = self.menuBar()

        self.file_menu = menu.addMenu("&File")
        self.file_menu.addAction(import_audio_file_action)

    def on_import_audio_file_action(self):
        (file_path, _) = QFileDialog.getOpenFileName(
            self, 'Select audio file', '', 'Audio Files (*.mp3 *.wav *.m4a)')
        if file_path == '':
            return
        self.new_import_window_triggered.emit((file_path, self.geometry()))


class RecordingTranscriberMainWindow(MainWindow):
    def __init__(self, parent: Optional[QWidget], *args) -> None:
        super().__init__(title='Live Recording', w=400, h=500, parent=parent, *args)

        central_widget = RecordingTranscriberWidget(self)
        central_widget.setContentsMargins(10, 10, 10, 10)
        self.setCentralWidget(central_widget)


class FileTranscriberMainWindow(MainWindow):
    def __init__(self, file_path: str, parent: Optional[QWidget], *args) -> None:
        super().__init__(title=get_short_file_path(
            file_path), w=400, h=180, parent=parent, *args)

        central_widget = FileTranscriberWidget(file_path, self)
        central_widget.setContentsMargins(10, 10, 10, 10)
        self.setCentralWidget(central_widget)


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
