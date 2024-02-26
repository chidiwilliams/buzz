import sys

from PyQt6.QtWidgets import QApplication

from buzz.__version__ import VERSION
from buzz.db.dao.transcription import TranscriptionDAO
from buzz.settings.settings import APP_NAME
from buzz.transcriber.transcriber import FileTranscriptionTask
from buzz.widgets.main_window import MainWindow


class Application(QApplication):
    window: MainWindow

    def __init__(self, transcription_dao: TranscriptionDAO) -> None:
        super().__init__(sys.argv)

        self.setApplicationName(APP_NAME)
        self.setApplicationVersion(VERSION)

        if sys.platform == "darwin":
            self.setStyle("Fusion")

        self.window = MainWindow(transcription_dao=transcription_dao)
        self.window.show()

    def add_task(self, task: FileTranscriptionTask):
        self.window.add_task(task)
