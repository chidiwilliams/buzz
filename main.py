import logging
import warnings

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from transcriber import Transcriber

logging.basicConfig(level=logging.DEBUG)
warnings.filterwarnings('ignore')


class TranscriberWorker(QObject):
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


class Application:
    def __init__(self) -> None:
        self.app = QApplication([])
        self.window = QWidget()

        layout = QVBoxLayout()

        record_button = QPushButton("Record")
        record_button.clicked.connect(self.on_click_record)

        stop_button = QPushButton("Stop")
        stop_button.clicked.connect(self.on_click_stop)

        self.text_box = QTextEdit()
        self.text_box.setReadOnly(True)

        layout.addWidget(record_button)
        layout.addWidget(stop_button)
        layout.addWidget(self.text_box)

        self.window.setLayout(layout)

    def on_next_text(self, text: str):
        self.text_box.append(text)

    def on_click_record(self):
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

    def on_click_stop(self):
        self.transcriber_worker.stop_recording()

    def start(self):
        self.window.show()
        self.app.exec()


app = Application()
app.start()
