import enum
import logging
import warnings

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from transcriber import Transcriber

logging.basicConfig(level=logging.DEBUG)
warnings.filterwarnings('ignore')


class TranscriberWorker(QObject):
    """
    TranscriberWorker holds a Transcriber and exports two signals: `text` and `finished`.
    `text` gets called when each new transcription is available, while `finished` gets
    called when the recording ends.
    """

    text = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.transcriber = Transcriber(text_callback=self.on_next_text)

    def run(self):
        self.transcriber.start_recording()
        self.finished.emit()

    def on_next_text(self, text: str):
        self.text.emit(text)

    def stop_recording(self):
        self.transcriber.stop_recording()


class Application(QObject):
    class Status(enum.Enum):
        RECORDING = enum.auto()
        STOPPED = enum.auto()

    current_status = Status.STOPPED
    status_signal = pyqtSignal(Status)

    def __init__(self, *args) -> None:
        super().__init__(*args)

        self.app = QApplication([])
        self.window = QWidget()

        layout = QVBoxLayout()

        button_layout = QHBoxLayout()

        self.record_button = QPushButton("Record")
        self.record_button.clicked.connect(self.on_click_record)

        button_layout.addWidget(self.record_button)
        button_layout.addStretch(1)

        self.text_box = QTextEdit()
        self.text_box.setReadOnly(True)

        layout.addLayout(button_layout)
        layout.addWidget(self.text_box)

        self.window.setLayout(layout)
        self.status_signal.connect(self.update_status)

    def on_next_text(self, text: str):
        self.text_box.append(text)

    def on_click_record(self):
        if self.current_status == self.Status.RECORDING:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        self.status_signal.emit(self.Status.RECORDING)

        # Thread needs to be attached to app object to live after end of method
        self.thread = QThread()

        self.transcriber_worker = TranscriberWorker()
        self.transcriber_worker.moveToThread(self.thread)

        self.thread.started.connect(self.transcriber_worker.run)
        self.transcriber_worker.finished.connect(self.thread.quit)
        self.transcriber_worker.finished.connect(
            self.transcriber_worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.transcriber_worker.text.connect(self.on_next_text)

        self.thread.start()

    def stop_recording(self):
        self.status_signal.emit(self.Status.STOPPED)
        self.transcriber_worker.stop_recording()

    def update_status(self, status: Status):
        self.current_status = status

        if status == self.Status.RECORDING:
            self.record_button.setText('Stop')
        else:
            self.record_button.setText('Record')

    def start(self):
        self.window.show()
        self.app.exec()


app = Application()
app.start()
