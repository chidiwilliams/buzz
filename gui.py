import enum
from typing import List, Optional, Tuple

import pyaudio
import whisper
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from whisper import tokenizer

from transcriber import Transcriber


class Label(QLabel):
    def __init__(self, name: str,  *args) -> None:
        super().__init__(name, *args)
        self.setStyleSheet('QLabel { color: #ddd }')


class AudioDevicesComboBox(QComboBox):
    """AudioDevicesComboBox displays a list of available audio input devices"""
    deviceChanged = pyqtSignal(int)

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.pyaudio = pyaudio.PyAudio()
        self.audio_devices = self.get_audio_devices()
        self.addItems(map(lambda device: device[1], self.audio_devices))
        self.currentIndexChanged.connect(self.on_index_changed)

    # https://stackoverflow.com/a/39677871/9830227
    def get_audio_devices(self) -> List[Tuple[int, str]]:
        audio_info = self.pyaudio.get_host_api_info_by_index(0)
        num_devices = audio_info.get('deviceCount')
        devices = []
        for i in range(0, num_devices):
            device_info = self.pyaudio.get_device_info_by_host_api_device_index(
                0, i)
            if (device_info.get('maxInputChannels')) > 0:
                devices.append((i, device_info.get('name')))
        return devices

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


class ModelsComboBox(QComboBox):
    """ModelsComboBox displays the list of available Whisper models for selection"""
    modelNameChanged = pyqtSignal(str)

    def __init__(self, default_model_name: str, *args) -> None:
        super().__init__(*args)
        self.models = whisper.available_models()
        self.addItems(map(self.label, self.models))
        self.currentIndexChanged.connect(self.on_index_changed)
        self.setCurrentText(default_model_name)

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
            'QTextEdit { padding-left: 5; padding-top: 5; padding-bottom: 5; padding-right: 5; background-color: #151515; border-radius: 6; background-color: #1e1e1e; }')


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
        else:
            self.setText('Record')


class TranscriberWorker(QObject):
    """
    TranscriberWorker wraps a `Transcriber` inside a QObject and exports signals
    that report when a new transcription is received or the recording is stopped.
    """

    text = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, model_name: str, language: Optional[str], input_device_index: Optional[int], *args) -> None:
        super().__init__(*args)
        self.transcriber = Transcriber(
            model_name=model_name, language=language, text_callback=self.on_next_text)
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

    def __init__(self) -> None:
        super().__init__([])

        self.window = QWidget()
        self.window.setFixedSize(400, 400)

        layout = QGridLayout()
        self.window.setLayout(layout)

        self.audio_devices_combo_box = AudioDevicesComboBox()
        self.audio_devices_combo_box.deviceChanged.connect(
            self.on_device_changed)
        self.selected_device_id = self.audio_devices_combo_box.get_default_device_id()

        record_button = RecordButton()
        record_button.statusChanged.connect(self.on_status_changed)

        self.text_box = TextDisplayBox()

        models_combo_box = ModelsComboBox(
            default_model_name=self.selected_model_name)
        models_combo_box.modelNameChanged.connect(self.on_model_changed)

        languages_combo_box = LanguagesComboBox(
            default_language=self.selected_language)
        languages_combo_box.languageChanged.connect(self.on_language_changed)

        layout.addWidget(Label('Model:'), 0, 0, 1, 3)
        layout.addWidget(models_combo_box, 0, 3, 1, 9)

        layout.addWidget(Label('Language:'), 1, 0, 1, 3)
        layout.addWidget(languages_combo_box, 1, 3, 1, 9)

        layout.addWidget(Label('Microphone:'), 2, 0, 1, 3)
        layout.addWidget(self.audio_devices_combo_box, 2, 3, 1, 9)

        layout.addWidget(record_button, 3, 9, 1, 3)

        layout.addWidget(self.text_box, 4, 0, 1, 12)

        self.window.show()

    # TODO: might be great to send when the text has been updated rather than appending
    def on_next_text(self, text: str):
        self.text_box.moveCursor(QTextCursor.MoveOperation.End)
        self.text_box.insertPlainText(text)
        self.text_box.moveCursor(QTextCursor.MoveOperation.End)

    def on_device_changed(self, device_id: int):
        self.selected_device_id = device_id

    def on_status_changed(self, status: RecordButton.Status):
        if status == RecordButton.Status.RECORDING:
            self.audio_devices_combo_box.setDisabled(True)
            self.start_recording()
        else:
            self.audio_devices_combo_box.setDisabled(False)
            self.stop_recording()

    def on_model_changed(self, model_name: str):
        self.selected_model_name = model_name

    def on_language_changed(self, language: str):
        self.selected_language = language

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
