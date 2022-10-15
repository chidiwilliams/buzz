import enum
import os
import platform
from typing import Dict, List, Optional, Tuple

import sounddevice
import whisper
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from whisper import tokenizer

import _whisper
from transcriber import (FileTranscriber, RecordingTranscriber, State, Status,
                         Task)


def get_platform_styles(all_platform_styles: Dict[str, str]):
    return all_platform_styles.get(platform.system(), '')


class FormLabel(QLabel):
    def __init__(self, name: str,  *args) -> None:
        super().__init__(name, *args)
        self.setStyleSheet('QLabel { text-align: right; }')
        self.setAlignment(Qt.AlignmentFlag(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight))


class AudioDevicesComboBox(QComboBox):
    """AudioDevicesComboBox displays a list of available audio input devices"""
    device_changed = pyqtSignal(int)
    audio_devices: List[Tuple[int, str]]

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.audio_devices = self.get_audio_devices()
        self.addItems(map(lambda device: device[1], self.audio_devices))
        self.currentIndexChanged.connect(self.on_index_changed)
        if self.get_default_device_id() != None and len(self.audio_devices) > 0:
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
    languageChanged = pyqtSignal(str)

    def __init__(self, default_language: str, *args) -> None:
        super().__init__(*args)

        whisper_languages = sorted(
            [(lang, tokenizer.LANGUAGES[lang].title())
             for lang in tokenizer.LANGUAGES.keys()],
            key=lambda lang: lang[1])
        self.languages = [('', 'Detect Language')] + whisper_languages

        self.addItems([lang[1] for lang in self.languages])
        self.currentIndexChanged.connect(self.on_index_changed)
        default_language_index = next((i for i, lang in enumerate(self.languages)
                                       if lang[0] == default_language), 0)
        self.setCurrentIndex(default_language_index)

    def on_index_changed(self, index: int):
        self.languageChanged.emit(self.languages[index][0])


class TasksComboBox(QComboBox):
    """TasksComboBox displays a list of tasks available to use with Whisper"""
    taskChanged = pyqtSignal(Task)

    def __init__(self, default_task: Task, *args) -> None:
        super().__init__(*args)
        self.tasks = [i for i in Task]
        self.addItems(map(lambda task: task.value.title(), self.tasks))
        self.currentIndexChanged.connect(self.on_index_changed)
        self.setCurrentText(default_task.value.title())

    def on_index_changed(self, index: int):
        self.taskChanged.emit(self.tasks[index])


class ModelsComboBox(QComboBox):
    """ModelsComboBox displays the list of available Whisper models for selection"""
    modelNameChanged = pyqtSignal(str)

    def __init__(self, default_model_name: str, *args) -> None:
        super().__init__(*args)
        self.models = whisper.available_models()
        self.addItems(map(self.label, self.models))
        self.currentIndexChanged.connect(self.on_index_changed)
        self.setCurrentText(self.label(default_model_name))

    def on_index_changed(self, index: int):
        self.modelNameChanged.emit(self.models[index])

    def label(self, model_name: str):
        name, lang = (model_name.split('.') + [None])[:2]
        if lang:
            return "%s (%s)" % (name.title(), lang.upper())
        return name.title()


class DelaysComboBox(QComboBox):
    """DelaysComboBox displays the list of available delays"""
    delay_changed = pyqtSignal(int)

    def __init__(self, default_delay: int, *args) -> None:
        super().__init__(*args)
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

    def __init__(self, *args) -> None:
        super().__init__(*args)
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

    def __init__(self, *args) -> None:
        super().__init__("Record", *args)
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


class ProgressDialog(QProgressDialog):
    def __init__(self, total_size: int, label_text='Downloading resources...', *args) -> None:
        super().__init__(label_text, 'Cancel', 0, total_size, *args)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setCancelButton(None)
        self.installEventFilter(self)
        # Don't show window close icons
        self.setWindowFlags(Qt.WindowType(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.CustomizeWindowHint))

    def closeEvent(self, event: QEvent):
        # Ignore close event from 'x' window icon
        event.ignore()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Don't close dialog when Return, Esc, or Enter is clicked
        if obj == self and \
                event.type() == QEvent.Type.KeyPress and \
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Enter):
            return True
        return super().eventFilter(obj, event)


class TranscriberWithSignal(QObject):
    """
    TranscriberWithSignal exports the text callback from a Transcriber
    as a QtSignal to allow updating the UI from a secondary thread.
    """

    status_changed = pyqtSignal(Status)

    def __init__(self, model: whisper.Whisper, language: Optional[str], task: Task, *args) -> None:
        super().__init__(*args)
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

    def __init__(self):
        super().__init__()

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


class FileTranscriberWidget(QWidget):
    selected_model_name = 'tiny'
    selected_language = 'en'
    selected_task = Task.TRANSCRIBE
    progress_dialog: Optional[ProgressDialog] = None
    transcribe_progress = pyqtSignal(tuple)

    def __init__(self, file_path: str) -> None:
        super().__init__()

        layout = QGridLayout()

        self.file_path = file_path

        self.models_combo_box = ModelsComboBox(
            default_model_name=self.selected_model_name)
        self.models_combo_box.modelNameChanged.connect(self.on_model_changed)

        self.languages_combo_box = LanguagesComboBox(
            default_language=self.selected_language)
        self.languages_combo_box.languageChanged.connect(
            self.on_language_changed)

        self.tasks_combo_box = TasksComboBox(
            default_task=Task.TRANSCRIBE)
        self.tasks_combo_box.taskChanged.connect(self.on_task_changed)

        self.run_button = QPushButton('Run')
        self.run_button.clicked.connect(self.on_click_run)
        self.run_button.setDefault(True)

        grid = (
            ((0, 5, FormLabel('Task:')), (5, 7, self.tasks_combo_box)),
            ((0, 5, FormLabel('Language:')), (5, 7, self.languages_combo_box)),
            ((0, 5, FormLabel('Model:')), (5, 7, self.models_combo_box)),
            ((9, 3, self.run_button),)
        )

        for (row_index, row) in enumerate(grid):
            for (_, cell) in enumerate(row):
                (col_offset, col_width, widget) = cell
                layout.addWidget(widget, row_index, col_offset, 1, col_width)

        self.setLayout(layout)

        self.transcribe_progress.connect(self.handle_transcribe_progress)

    def on_model_changed(self, model_name: str):
        self.selected_model_name = model_name

    def on_language_changed(self, language: str):
        self.selected_language = language

    def on_task_changed(self, task: Task):
        self.selected_task = task

    def on_click_run(self):
        default_path = FileTranscriber.get_default_output_file_path(self.file_path)
        (output_file, _) = QFileDialog.getSaveFileName(
            self, 'Save File', default_path, 'Text files (*.txt)')

        if output_file == '':
            return

        self.run_button.setDisabled(True)
        model = _whisper.load_model(
            self.selected_model_name, on_download_model_chunk=self.on_download_model_progress)

        file_transcriber = FileTranscriber(
            model=model, file_path=self.file_path,
            language=self.selected_language, task=self.selected_task,
            output_file_path=output_file, progress_callback=self.on_transcribe_model_progress)
        file_transcriber.start()

    def on_download_model_progress(self, current_size: int, total_size: int):
        if self.progress_dialog == None:
            self.progress_dialog = ProgressDialog(
                total_size=total_size, label_text='Downloading resources...')
        else:
            self.progress_dialog.setValue(current_size)
            if current_size == total_size:
                self.run_button.setDisabled(False)

    def on_transcribe_model_progress(self, current_size: int, total_size: int):
        self.transcribe_progress.emit((current_size, total_size))

    def handle_transcribe_progress(self, progress: Tuple[int, int]):
        (current_size, total_size) = progress
        if self.progress_dialog == None:
            self.progress_dialog = ProgressDialog(
                total_size=total_size, label_text='Processing...')
        else:
            self.progress_dialog.setValue(current_size)
            if current_size == total_size:
                self.run_button.setDisabled(False)


class RecordingTranscriberWidget(QWidget):
    current_status = RecordButton.Status.STOPPED
    selected_model_name = 'tiny'
    selected_language = 'en'
    selected_device_id: Optional[int]
    selected_delay = 10
    selected_task = Task.TRANSCRIBE
    progress_dialog: Optional[ProgressDialog] = None

    def __init__(self) -> None:
        super().__init__()

        layout = QGridLayout()

        self.models_combo_box = ModelsComboBox(
            default_model_name=self.selected_model_name)
        self.models_combo_box.modelNameChanged.connect(self.on_model_changed)

        self.languages_combo_box = LanguagesComboBox(
            default_language=self.selected_language)
        self.languages_combo_box.languageChanged.connect(
            self.on_language_changed)

        self.audio_devices_combo_box = AudioDevicesComboBox()
        self.audio_devices_combo_box.device_changed.connect(
            self.on_device_changed)
        self.selected_device_id = self.audio_devices_combo_box.get_default_device_id()

        self.tasks_combo_box = TasksComboBox(
            default_task=Task.TRANSCRIBE)
        self.tasks_combo_box.taskChanged.connect(self.on_task_changed)

        delays_combo_box = DelaysComboBox(default_delay=self.selected_delay)
        delays_combo_box.delay_changed.connect(self.on_delay_changed)

        self.timer_label = TimerLabel()

        self.record_button = RecordButton()
        self.record_button.status_changed.connect(self.on_status_changed)

        self.text_box = TextDisplayBox()

        grid = (
            ((0, 5, FormLabel('Model:')), (5, 7, self.models_combo_box)),
            ((0, 5, FormLabel('Language:')), (5, 7, self.languages_combo_box)),
            ((0, 5, FormLabel('Task:')), (5, 7, self.tasks_combo_box)),
            ((0, 5, FormLabel('Microphone:')),
             (5, 7, self.audio_devices_combo_box)),
            ((0, 5, FormLabel('Delay:')), (5, 7, delays_combo_box)),
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

    def on_model_changed(self, model_name: str):
        self.selected_model_name = model_name

    def on_language_changed(self, language: str):
        self.selected_language = language

    def on_task_changed(self, task: Task):
        self.selected_task = task

    def on_delay_changed(self, delay: int):
        self.selected_delay = delay

    def start_recording(self):
        self.record_button.setDisabled(True)

        model = _whisper.load_model(
            self.selected_model_name, on_download_model_chunk=self.on_download_model_chunk)

        self.record_button.setDisabled(False)
        # Clear text box placeholder because the first chunk takes a while to process
        self.text_box.setPlaceholderText('')
        self.timer_label.start_timer()

        self.transcriber = TranscriberWithSignal(
            model=model,
            language=self.selected_language if self.selected_language != '' else None,
            task=self.selected_task,
        )
        self.transcriber.status_changed.connect(
            self.on_transcriber_status_changed)
        self.transcriber.start_recording(
            input_device_index=self.selected_device_id,
            block_duration=self.selected_delay,
        )

    def on_download_model_chunk(self, current_size: int, total_size: int):
        if self.progress_dialog == None:
            self.progress_dialog = ProgressDialog(
                total_size=total_size)
        else:
            self.progress_dialog.setValue(current_size)

    def stop_recording(self):
        self.transcriber.stop_recording()
        self.timer_label.stop_timer()


class MainWindow(QMainWindow):
    new_import_window_triggered = pyqtSignal(tuple)

    def __init__(self, window_title: str,
                 central_widget: QWidget,
                 w=400, h=500,
                 *args):
        super().__init__(*args)

        self.setFixedSize(w, h)
        self.setWindowTitle(f'{window_title} — Buzz')

        self.central_widget = central_widget
        self.central_widget.setContentsMargins(10, 10, 10, 10)
        self.setCentralWidget(self.central_widget)

        import_audio_file_action = QAction("&Import Audio File...", self)
        import_audio_file_action.triggered.connect(
            self.on_import_audio_file_action)
        import_audio_file_action.setShortcut(QKeySequence.fromString('Ctrl+O'))

        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        file_menu.addAction(import_audio_file_action)

    def on_import_audio_file_action(self):
        (file_path, _) = QFileDialog.getOpenFileName(
            self, 'Select audio file', '', 'Audio Files (*.mp3 *.wav *.m4a)')
        if file_path == '':
            return
        self.new_import_window_triggered.emit((file_path, self.geometry()))


class Application(QApplication):
    windows: List[MainWindow] = []

    def __init__(self) -> None:
        super().__init__([])

        window = MainWindow(window_title='Live Recording',
                            central_widget=RecordingTranscriberWidget())
        window.new_import_window_triggered.connect(self.open_import_window)
        window.show()

        self.windows.append(window)

    def open_import_window(self, window_config: Tuple[str, QRect]):
        (file_path, geometry) = window_config

        window = MainWindow(
            w=400, h=180, central_widget=FileTranscriberWidget(file_path=file_path),
            window_title=os.path.basename(file_path))

        # Set window to open at an offset from the calling sibling
        OFFSET = 35
        geometry = QRect(geometry.left() + OFFSET, geometry.top() + OFFSET,
                         geometry.width(), geometry.height())
        window.setGeometry(geometry)
        self.windows.append(window)

        window.new_import_window_triggered.connect(self.open_import_window)
        window.show()
