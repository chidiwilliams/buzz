import sys
import darkdetect

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor

from buzz.__version__ import VERSION
from buzz.db.dao.transcription_dao import TranscriptionDAO
from buzz.db.dao.transcription_segment_dao import TranscriptionSegmentDAO
from buzz.db.db import setup_app_db
from buzz.db.service.transcription_service import TranscriptionService
from buzz.settings.settings import APP_NAME, Settings

from buzz.transcriber.transcriber import FileTranscriptionTask
from buzz.widgets.main_window import MainWindow


class Application(QApplication):
    window: MainWindow

    def __init__(self, argv: list) -> None:
        super().__init__(argv)

        self.setApplicationName(APP_NAME)
        self.setApplicationVersion(VERSION)

        self.settings = Settings()
        font_size = self.settings.value(
            key=Settings.Key.FONT_SIZE, default_value=self.font().pointSize()
        )

        if sys.platform == "darwin":
            self.setFont(QFont("SF Pro", font_size))
        else:
            self.setFont(QFont(self.font().family(), font_size))

        if sys.platform.startswith("win") and darkdetect.isDark():
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor("#121212"))
            palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#2e2e2e"))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#000000"))
            palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.Button, QColor("#1e1e1e"))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.BrightText, QColor("#ff0000"))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))

            self.setPalette(palette)

        db = setup_app_db()
        transcription_service = TranscriptionService(
            TranscriptionDAO(db), TranscriptionSegmentDAO(db)
        )

        self.window = MainWindow(transcription_service)
        self.window.show()

    def add_task(self, task: FileTranscriptionTask):
        self.window.add_task(task)
