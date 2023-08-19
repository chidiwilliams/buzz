import sys

from PyQt6.QtWidgets import QApplication

from buzz.__version__ import VERSION
from buzz.settings.settings import APP_NAME
from buzz.transcriber import FileTranscriptionTask
from buzz.widgets.main_window import MainWindow


class Application(QApplication):
    window: MainWindow

    def __init__(self) -> None:
        super().__init__(sys.argv)

        self.setApplicationName(APP_NAME)
        self.setApplicationVersion(VERSION)

        if sys.platform == "darwin":
            self.setStyle("Fusion")

        self.window = MainWindow()
        self.window.show()

    def add_task(self, task: FileTranscriptionTask):
        self.window.add_task(task)
