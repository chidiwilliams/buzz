import enum
from typing import List, Optional, Tuple

import sounddevice
import whisper
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from whisper import tokenizer

from transcriber import Transcriber


class Label(QLabel):
    def __init__(self, name: str,  *args) -> None:
        super().__init__(name, *args)
        self.setStyleSheet('QLabel { color: #ddd; text-align: right; }')
        self.setAlignment(Qt.AlignmentFlag(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight))


class AudioDevicesComboBox(QComboBox):
    """AudioDevicesComboBox displays a list of available audio input devices"""
    deviceChanged = pyqtSignal(int)

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

    def get_default_device_id(self):
        return self.audio_devices[0][0]


class LanguagesComboBox(QComboBox):
    """LanguagesComboBox displays a list of languages available to use with Whisper"""
    languageChanged = pyqtSignal(str)

    def __init__(self, default_language: str, *args) -> None:
        super().__init__(*args)
        self.languages = {'': 'Detect language', **tokenizer.LANGUAGES}
        self.addItems(map(lambda lang: lang.title(), self.languages.values()))
        self.currentIndexChanged.connect(self.on_index_changed)
        self.setCurrentText(self.languages.get(default_language, '').title())

    def on_index_changed(self, index: int):
        key = list(self.languages.keys())[index]
        self.languageChanged.emit(key)


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


class TextDisplayBox(QTextEdit):
    """TextDisplayBox is a read-only textbox"""

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.setReadOnly(True)
        self.setPlaceholderText('Click Record to begin...')
        self.setStyleSheet(
            '''QTextEdit {
                padding-left: 5;
                padding-top: 5;
                padding-bottom: 5;
                padding-right: 5;
                border-radius: 6;
                background-color: #252525;
                color: #dfdfdf;
                }''')


class RecordButton(QPushButton):
    class Status(enum.Enum):
        RECORDING = enum.auto()
        STOPPED = enum.auto()

    current_status = Status.STOPPED
    statusChanged = pyqtSignal(Status)

    def __init__(self, *args) -> None:
        super().__init__("Record", *args)
        self.clicked.connect(self.on_click_record)
        self.statusChanged.connect(self.on_status_changed)
        self.setDefault(True)

    def on_click_record(self):
        current_status: RecordButton.Status
        if self.current_status == self.Status.RECORDING:
            current_status = self.Status.STOPPED
        else:
            current_status = self.Status.RECORDING

        self.statusChanged.emit(current_status)

    def on_status_changed(self, status: Status):
        self.current_status = status
        if status == self.Status.RECORDING:
            self.setText('Stop')
            self.setDefault(False)
        else:
            self.setText('Record')
            self.setDefault(True)


class TranscriberWorker(QObject):
    """
    TranscriberWorker wraps a `Transcriber` inside a QObject and exports signals
    that report when a new transcription is received or the recording is stopped.
    """

    text = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, model_name: str, language: Optional[str],
                 input_device_index: Optional[int], task: Transcriber.Task, *args) -> None:
        super().__init__(*args)
        self.transcriber = Transcriber(
            model_name=model_name, language=language,
            text_callback=self.on_next_text, task=task)
        self.input_device_index = input_device_index

    def run(self):
        self.transcriber.start_recording(
            input_device_index=self.input_device_index)
        self.finished.emit()

    def on_next_text(self, text: str):
        self.text.emit(text.strip())

    def stop_recording(self):
        self.transcriber.stop_recording()


class Application(QApplication):
    current_status = RecordButton.Status.STOPPED
    thread: Optional[QThread] = None
    selected_model_name = 'tiny'
    selected_language = 'en'
    selected_device_id: int
    selected_task = Transcriber.Task.TRANSCRIBE

    def __init__(self) -> None:
        super().__init__([])

        self.window = QWidget()
        self.window.setFixedSize(400, 400)

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

        record_button = RecordButton()
        record_button.statusChanged.connect(self.on_status_changed)

        self.text_box = TextDisplayBox()

        grid = ((Label('Model:'), self.models_combo_box),
                (Label('Language:'), self.languages_combo_box),
                (Label('Microphone:'), self.audio_devices_combo_box),
                (Label('Task:'), self.tasks_combo_box))

        widths = (4, 8)
        for (row_index, row) in enumerate(grid):
            for (col_index, cell) in enumerate(row):
                layout.addWidget(cell,
                                 row_index, 0 if col_index == 0 else widths[col_index-1],
                                 1, widths[col_index])

        layout.addWidget(record_button, 4, 9, 1, 3)

        layout.addWidget(self.text_box, 5, 0, 1, 12)

        self.window.show()

    # TODO: might be great to send when the text has been updated rather than appending
    def on_next_text(self, text: str):
        self.text_box.moveCursor(QTextCursor.MoveOperation.End)
        self.text_box.insertPlainText(text + ' ')
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

    def start_recording(self):
        # Clear text box placeholder because the first chunk takes a while to process
        self.text_box.setPlaceholderText('')

        # Transcribing the recording chunks is a blocking
        # process, so we handle this in a new thread

        # Wait for previous thread to complete in case stop_recording isn't yet done
        if self.thread != None:
            self.thread.wait()

        self.thread = QThread()

        self.transcriber_worker = TranscriberWorker(
            input_device_index=self.selected_device_id,
            model_name=self.selected_model_name,
            language=self.selected_language if self.selected_language != '' else None,
            task=self.selected_task
        )
        self.transcriber_worker.moveToThread(self.thread)

        # Connect worker and thread such that the worker runs once
        # the thread starts and the thread quits once the worker finishes
        self.thread.started.connect(self.transcriber_worker.run)
        self.transcriber_worker.finished.connect(self.thread.quit)
        self.transcriber_worker.finished.connect(
            self.transcriber_worker.deleteLater)
        self.thread.finished.connect(self.clean_up_thread)

        self.transcriber_worker.text.connect(self.on_next_text)

        self.thread.start()

    def clean_up_thread(self):
        self.thread.deleteLater()
        self.thread = None

    def stop_recording(self):
        self.transcriber_worker.stop_recording()
