import enum
import platform
from typing import Dict, List, Optional, Tuple

import sounddevice
import whisper
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from whisper import tokenizer

import _whisper
from transcriber import Transcriber


def get_platform_styles(all_platform_styles: Dict[str, str]):
    return all_platform_styles.get(platform.system(), '')


class Label(QLabel):
    def __init__(self, name: str,  *args) -> None:
        super().__init__(name, *args)
        self.setStyleSheet('QLabel { text-align: right; }')
        self.setAlignment(Qt.AlignmentFlag(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight))


class AudioDevicesComboBox(QComboBox):
    """AudioDevicesComboBox displays a list of available audio input devices"""
    deviceChanged = pyqtSignal(int)
    audio_devices: List[Tuple[int, str]]

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.audio_devices = self.get_audio_devices()
        self.addItems(map(lambda device: device[1], self.audio_devices))
        self.currentIndexChanged.connect(self.on_index_changed)

    def get_audio_devices(self) -> List[Tuple[int, str]]:
        devices: sounddevice.DeviceList = sounddevice.query_devices()
        input_devices = filter(
            lambda device: device.get('max_input_channels') > 0, devices)
        return list(map(lambda device: (device.get('index'), device.get('name')), input_devices))

    def on_index_changed(self, index: int):
        self.deviceChanged.emit(self.audio_devices[index][0])

    def get_default_device_id(self) -> Optional[int]:
        return self.audio_devices[0][0] if len(self.audio_devices) > 0 else None


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
    taskChanged = pyqtSignal(Transcriber.Task)

    def __init__(self, default_task: Transcriber.Task, *args) -> None:
        super().__init__(*args)
        self.tasks = [i for i in Transcriber.Task]
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


class DownloadModelProgressDialog(QProgressDialog):
    def __init__(self, total_size: int, *args) -> None:
        super().__init__('Downloading resources...', 'Cancel', 0, total_size, *args)
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

    text_changed = pyqtSignal(str)

    def __init__(self, model: whisper.Whisper, language: Optional[str], task: Transcriber.Task, *args) -> None:
        super().__init__(*args)
        self.transcriber = Transcriber(
            model=model, language=language,
            text_callback=self.on_next_text, task=task)

    def start_recording(self, input_device_index: Optional[int], block_duration: int):
        self.transcriber.start_recording(
            input_device_index=input_device_index,
            block_duration=block_duration,
        )

    def on_next_text(self, text: str):
        self.text_changed.emit(text.strip())

    def stop_recording(self):
        self.transcriber.stop_recording()


class Application(QApplication):
    current_status = RecordButton.Status.STOPPED
    selected_model_name = 'tiny'
    selected_language = 'en'
    selected_device_id: Optional[int]
    selected_delay = 10
    selected_task = Transcriber.Task.TRANSCRIBE
    progress_dialog: Optional[DownloadModelProgressDialog] = None

    def __init__(self) -> None:
        super().__init__([])

        self.window = QWidget()
        self.window.setFixedSize(400, 500)
        self.window.setWindowTitle('Buzz')

        layout = QGridLayout()
        self.window.setLayout(layout)

        self.models_combo_box = ModelsComboBox(
            default_model_name=self.selected_model_name)
        self.models_combo_box.modelNameChanged.connect(self.on_model_changed)

        self.languages_combo_box = LanguagesComboBox(
            default_language=self.selected_language)
        self.languages_combo_box.languageChanged.connect(
            self.on_language_changed)

        self.audio_devices_combo_box = AudioDevicesComboBox()
        self.audio_devices_combo_box.deviceChanged.connect(
            self.on_device_changed)
        self.selected_device_id = self.audio_devices_combo_box.get_default_device_id()

        self.tasks_combo_box = TasksComboBox(
            default_task=Transcriber.Task.TRANSCRIBE)
        self.tasks_combo_box.taskChanged.connect(self.on_task_changed)

        delays_combo_box = DelaysComboBox(default_delay=self.selected_delay)
        delays_combo_box.delay_changed.connect(self.on_delay_changed)

        self.record_button = RecordButton()
        self.record_button.status_changed.connect(self.on_status_changed)

        self.text_box = TextDisplayBox()

        grid = (
            ((0, 5, Label('Model:')), (5, 7, self.models_combo_box)),
            ((0, 5, Label('Language:')), (5, 7, self.languages_combo_box)),
            ((0, 5, Label('Task:')), (5, 7, self.tasks_combo_box)),
            ((0, 5, Label('Microphone:')), (5, 7, self.audio_devices_combo_box)),
            ((0, 5, Label('Delay:')), (5, 7, delays_combo_box)),
            ((9, 3, self.record_button),),
            ((0, 12, self.text_box),),
        )

        for (row_index, row) in enumerate(grid):
            for (_, cell) in enumerate(row):
                (col_offset, col_width, widget) = cell
                layout.addWidget(widget, row_index, col_offset, 1, col_width)

        self.window.show()

    # TODO: might be great to send when the text has been updated rather than appending
    def on_text_changed(self, text: str):
        if len(text) > 0:
            self.text_box.moveCursor(QTextCursor.MoveOperation.End)
            self.text_box.insertPlainText(text + '\n\n')
            self.text_box.moveCursor(QTextCursor.MoveOperation.End)

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

    def on_task_changed(self, task: Transcriber.Task):
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

        self.transcriber = TranscriberWithSignal(
            model=model,
            language=self.selected_language if self.selected_language != '' else None,
            task=self.selected_task,
        )
        self.transcriber.text_changed.connect(self.on_text_changed)
        self.transcriber.start_recording(
            input_device_index=self.selected_device_id,
            block_duration=self.selected_delay,
        )

    def on_download_model_chunk(self, current_size: int, total_size: int):
        if self.progress_dialog == None:
            self.progress_dialog = DownloadModelProgressDialog(
                total_size=total_size)
        else:
            self.progress_dialog.setValue(current_size)

    def stop_recording(self):
        self.transcriber.stop_recording()
