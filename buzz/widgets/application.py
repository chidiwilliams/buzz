import logging
import os
import sys
import locale
import platform
import threading
import darkdetect

from posthog import Posthog

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QStyleFactory

from buzz.__version__ import VERSION
from buzz.db.dao.transcription_dao import TranscriptionDAO
from buzz.db.dao.transcription_segment_dao import TranscriptionSegmentDAO
from buzz.db.db import setup_app_db
from buzz.db.meeting_library_repository import QSqlMeetingLibraryRepository
from buzz.db.meeting_speaker_repository import QSqlMeetingSpeakerRepository
from buzz.db.meeting_storage_repository import QSqlMeetingRepository
from buzz.db.meeting_transcription_repository import QSqlMeetingTranscriptionRepository
from buzz.db.service.transcription_service import TranscriptionService
from buzz.meeting.final_transcription import FinalTranscriptionReadService
from buzz.meeting.meeting_detail import MeetingDetailService
from buzz.meeting.meeting_library import MeetingLibraryService
from buzz.meeting.meeting_storage import MeetingStorage
from buzz.meeting.speaker_review import MeetingSpeakerReviewService
from buzz.settings.settings import APP_NAME, Settings

from buzz.transcriber.transcriber import FileTranscriptionTask
from buzz.widgets.audio_player import AudioPlayer
from buzz.widgets.main_window import MainWindow
from buzz.meeting.meeting_workflow import MeetingWorkflow
from buzz.meeting.meeting_transcriber_adapter import MeetingTrackTranscriber
from buzz.widgets.meeting_mode import MeetingModeController
from buzz.widgets.meeting_final_transcription import MeetingFinalTranscription


def _build_main_window(database) -> MainWindow:
    transcription_service = TranscriptionService(
        TranscriptionDAO(database), TranscriptionSegmentDAO(database)
    )
    meeting_library_repository = QSqlMeetingLibraryRepository(database)
    meeting_library_service = MeetingLibraryService(meeting_library_repository)
    meeting_storage = MeetingStorage(QSqlMeetingRepository(database))
    transcription_repository = QSqlMeetingTranscriptionRepository(database)
    final_transcription_reader = FinalTranscriptionReadService(transcription_repository)
    speaker_review_service = MeetingSpeakerReviewService(
        QSqlMeetingSpeakerRepository(database), final_transcription_reader
    )
    meeting_detail_service = MeetingDetailService(
        meeting_storage,
        final_transcription_reader,
        speaker_review_service,
    )
    meeting_final = MeetingFinalTranscription(
        meeting_storage, transcription_repository, MeetingTrackTranscriber()
    )
    window = MainWindow(
        transcription_service,
        meeting_library_service,
        meeting_detail_service,
        speaker_review_service,
        AudioPlayer,
        MeetingModeController(MeetingWorkflow(meeting_storage)),
        meeting_final,
    )
    meeting_final.recover()
    return window


class Application(QApplication):
    window: MainWindow

    def __init__(self, argv: list) -> None:
        super().__init__(argv)

        self.setApplicationName(APP_NAME)
        self.setApplicationVersion(VERSION)
        self.hide_main_window = False

        if darkdetect.isDark():
            self.styleHints().setColorScheme(Qt.ColorScheme.Dark)
            self.setStyleSheet(
                "QCheckBox::indicator:unchecked,"
                " QAbstractItemView::indicator:unchecked"
                " { border: 1px solid white; }"
            )

        if sys.platform.startswith("win"):
            self.setStyle(QStyleFactory.create("Fusion"))

        self.settings = Settings()
        logging.debug(f"Settings filename: {self.settings.settings.fileName()}")

        # Set BUZZ_FORCE_CPU environment variable if Force CPU setting is enabled
        force_cpu_enabled = self.settings.value(
            key=Settings.Key.FORCE_CPU, default_value=False
        )
        if force_cpu_enabled:
            os.environ["BUZZ_FORCE_CPU"] = "true"

        # Set BUZZ_REDUCE_GPU_MEMORY environment variable if Reduce GPU RAM setting is enabled
        reduce_gpu_memory_enabled = self.settings.value(
            key=Settings.Key.REDUCE_GPU_MEMORY, default_value=False
        )
        if reduce_gpu_memory_enabled:
            os.environ["BUZZ_REDUCE_GPU_MEMORY"] = "true"

        font_size = self.settings.value(
            key=Settings.Key.FONT_SIZE, default_value=self.font().pointSize()
        )

        if sys.platform == "darwin":
            self.setFont(QFont("SF Pro", font_size))
        else:
            self.setFont(QFont(self.font().family(), font_size))

        self.db = setup_app_db()
        self.window = _build_main_window(self.db)

        disable_telemetry = os.getenv("BUZZ_DISABLE_TELEMETRY", None)

        if not disable_telemetry:
            posthog = Posthog(
                project_api_key="phc_NqZQUw8NcxfSXsbtk5eCFylmCQpp4FuNnd6ocPAzg2f",
                host="https://us.i.posthog.com",
            )
            posthog.capture(
                distinct_id=self.settings.get_user_identifier(),
                event="app_launched",
                properties={
                    "app": VERSION,
                    "locale": locale.getlocale(),
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                    "version": platform.version(),
                },
            )
            threading.Thread(target=posthog.shutdown, daemon=True).start()

        logging.debug(
            f"Launching Buzz: {VERSION}, "
            f"locale: {locale.getlocale()}, "
            f"system: {platform.system()}, "
            f"release: {platform.release()}, "
            f"machine: {platform.machine()}, "
            f"version: {platform.version()}, "
        )

    def show_main_window(self):
        if not self.hide_main_window:
            self.window.show()

    def event(self, event):
        if event.type() == QEvent.Type.Quit and hasattr(self, "window"):
            if not self.window.close():
                return True
        return super().event(event)

    def add_task(self, task: FileTranscriptionTask, quit_on_complete: bool = False):
        self.window.quit_on_complete = quit_on_complete
        self.window.add_task(task)

    def close_database(self):
        from buzz.db.db import close_app_db

        close_app_db()
