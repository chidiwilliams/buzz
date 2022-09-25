import enum
from typing import List, Tuple

import pyaudio
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from transcriber import Transcriber


class AudioDevicesComboBox(QComboBox):
    """AudioDevicesComboBox is a combo box for selecting audio devices."""
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
        pass


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
        current_status: self.Status
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

    def __init__(self, input_device_index: int = None, *args) -> None:
        super().__init__(*args)
        self.transcriber = Transcriber(text_callback=self.on_next_text)
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
    selected_device_id: int = None

    def __init__(self) -> None:
        super().__init__([])

        self.setStyle("fusion")
        self.setStyleSheet("""QComboBox {
            color: #eee;
        }""")

        self.window = QWidget()
        self.window.setFixedSize(400, 400)

        layout = QVBoxLayout()

        self.audio_devices_combo_box = AudioDevicesComboBox()
        self.audio_devices_combo_box.deviceChanged.connect(
            self.on_device_changed)

        self.record_button = RecordButton()
        self.record_button.statusChanged.connect(self.on_status_changed)

        self.text_box = self.get_text_box()

        layout.addLayout(self.get_audio_devices_row(
            self.audio_devices_combo_box))
        layout.addLayout(self.get_button_row(self.record_button))
        layout.addWidget(self.text_box)

        self.window.setLayout(layout)
        self.window.show()

    def get_audio_devices_row(self, audio_devices_combo_box: AudioDevicesComboBox):
        row = QHBoxLayout()

        label = QLabel()
        label.setText('Select microphone:')
        label.setStyleSheet('QLabel { color: #ddd }')

        row.addWidget(label)
        row.addWidget(audio_devices_combo_box)
        row.addStretch(1)
        return row

    def get_button_row(self, record_button: RecordButton):
        row = QHBoxLayout()
        row.addWidget(record_button)
        row.addStretch(1)
        return row

    def get_text_box(self):
        box = QTextEdit()
        box.setReadOnly(True)
        box.setPlaceholderText('Click Record to begin...')
        return box

    def on_next_text(self, text: str):
        self.text_box.append(text)

    def on_device_changed(self, device_id: int):
        self.selected_device_id = device_id

    def on_status_changed(self, status: RecordButton.Status):
        if status == RecordButton.Status.RECORDING:
            self.audio_devices_combo_box.setDisabled(True)
            self.start_recording()
        else:
            self.audio_devices_combo_box.setDisabled(False)
            self.stop_recording()

    def start_recording(self):
        # Thread needs to be attached to app object to live after end of method
        self.thread = QThread()

        self.transcriber_worker = TranscriberWorker(
            input_device_index=self.selected_device_id)
        self.transcriber_worker.moveToThread(self.thread)

        self.thread.started.connect(self.transcriber_worker.run)
        self.transcriber_worker.finished.connect(self.thread.quit)
        self.transcriber_worker.finished.connect(
            self.transcriber_worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.transcriber_worker.text.connect(self.on_next_text)

        self.thread.start()

    def stop_recording(self):
        self.transcriber_worker.stop_recording()
