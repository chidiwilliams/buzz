import logging
import os
import sys
import locale
import platform
import darkdetect

from posthog import Posthog

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QStyleFactory

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
        self.hide_main_window = False

        if darkdetect.isDark():
            self.styleHints().setColorScheme(Qt.ColorScheme.Dark)

        self.setStyle(QStyleFactory.create("Fusion"))
        self.setPalette(QApplication.style().standardPalette())

        self.settings = Settings()
        font_size = self.settings.value(
            key=Settings.Key.FONT_SIZE, default_value=self.font().pointSize()
        )

        if sys.platform == "darwin":
            self.setFont(QFont("SF Pro", font_size))
        else:
            self.setFont(QFont(self.font().family(), font_size))

        db = setup_app_db()
        transcription_service = TranscriptionService(
            TranscriptionDAO(db), TranscriptionSegmentDAO(db)
        )

        self.window = MainWindow(transcription_service)

        disable_telemetry = os.getenv("BUZZ_DISABLE_TELEMETRY", None)

        if not disable_telemetry:
            posthog = Posthog(project_api_key='phc_NqZQUw8NcxfSXsbtk5eCFylmCQpp4FuNnd6ocPAzg2f',
                              host='https://us.i.posthog.com')
            posthog.capture(distinct_id=self.settings.get_user_identifier(), event="app_launched", properties={
                "app": VERSION,
                "locale": locale.getlocale(),
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "version": platform.version(),
            })

        logging.debug(f"Launching Buzz: {VERSION}, " 
                      f"locale: {locale.getlocale()}, "
                      f"system: {platform.system()}, "
                      f"release: {platform.release()}, "
                      f"machine: {platform.machine()}, "
                      f"version: {platform.version()}, ")

    def show_main_window(self):
        if not self.hide_main_window:
            self.window.show()

    def add_task(self, task: FileTranscriptionTask, quit_on_complete: bool = False):
        self.window.quit_on_complete = quit_on_complete
        self.window.add_task(task)
