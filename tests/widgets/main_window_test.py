import logging
import os
import shutil
import tempfile
from functools import partial
from typing import List
from unittest.mock import Mock, call, patch
from uuid import UUID

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QMessageBox,
    QPushButton,
    QToolBar,
    QTableView,
)
from pytestqt.qtbot import QtBot

from buzz.locale import _
from buzz.meeting.meeting_library import MeetingLibraryService
from buzz.meeting.meeting_detail import MeetingDetailNotFoundError, MeetingDetailService
from buzz.meeting.speaker_review import MeetingSpeakerReviewService
from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import (
    Task,
    OutputFormat,
    Segment,
    FileTranscriptionTask,
)
from buzz.transcriber.whisper_file_transcriber import (
    WhisperFileTranscriber,
    check_file_has_audio_stream,
)
from buzz.widgets.main_window import MainWindow as ProductionMainWindow
from buzz.widgets.meetings_library_widget import MeetingsLibraryWidget
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)
from buzz.widgets.transcriber.file_transcriber_widget import FileTranscriberWidget
from buzz.widgets.transcription_tasks_table_widget import (
    TranscriptionTasksTableWidget,
)

mock_transcriptions: List[Transcription] = [
    Transcription(status="completed"),
    Transcription(status="canceled"),
    Transcription(status="failed", error_message=_("Error")),
]
fake_meeting_library_service = Mock(spec=MeetingLibraryService)
fake_meeting_detail_service = Mock(spec=MeetingDetailService)
fake_speaker_review_service = Mock(spec=MeetingSpeakerReviewService)
fake_preview_player_factory = Mock()
MainWindow = partial(
    ProductionMainWindow,
    meeting_detail_service=fake_meeting_detail_service,
    meeting_speaker_review_service=fake_speaker_review_service,
    preview_player_factory=fake_preview_player_factory,
)


@pytest.fixture(scope="session")
def qapp_cls():
    return QApplication


@pytest.fixture(autouse=True)
def disable_plugin_initialization(monkeypatch):
    monkeypatch.setattr(
        "buzz.widgets.main_window.PluginManager.initialize", lambda self: None
    )


def get_test_asset(filename: str):
    return os.path.join(os.path.dirname(__file__), "../../testdata/", filename)


class _LocalArtifactWhisperFileTranscriber(WhisperFileTranscriber):
    """Keep MainWindow URL coverage independent of a downloaded ASR model."""

    seen_tasks = []

    def transcribe(self) -> List[Segment]:
        type(self).seen_tasks.append(self.transcription_task)
        self.progress.emit((0, 100))
        check_file_has_audio_stream(self.transcription_task.file_path)
        self.progress.emit((100, 100))
        return [Segment(start=0, end=100, text="local test transcript")]


class _LocalModel(TranscriptionModel):
    def __init__(self, model_path: str):
        super().__init__(
            model_type=ModelType.WHISPER,
            whisper_model_size=WhisperModelSize.TINY,
        )
        self.model_path = model_path

    def get_local_model_path(self):
        return self.model_path


class TestMainWindow:
    def test_meetings_action_reuses_one_window_and_refreshes_once_per_trigger(
        self, qtbot, transcription_service
    ):
        meeting_service = Mock(spec=MeetingLibraryService)
        library_window = Mock()
        with patch(
            "buzz.widgets.main_window.MeetingsLibraryWidget",
            return_value=library_window,
        ) as library_widget_type:
            window = MainWindow(transcription_service, meeting_service)
            qtbot.add_widget(window)

            window.menu_bar.meetings_action.trigger()

            library_widget_type.assert_called_once_with(
                service=meeting_service,
                parent=window,
                flags=Qt.WindowType.Window,
            )
            assert window.meetings_library_widget is library_window
            library_window.refresh.assert_called_once_with()
            library_window.show.assert_called_once_with()
            library_window.raise_.assert_called_once_with()
            library_window.activateWindow.assert_called_once_with()

            window.menu_bar.meetings_action.trigger()

            library_widget_type.assert_called_once()
            assert library_window.refresh.call_count == 2
            assert library_window.show.call_count == 2
            assert library_window.raise_.call_count == 2
            assert library_window.activateWindow.call_count == 2

            library_window.close()
            window.menu_bar.meetings_action.trigger()

            library_widget_type.assert_called_once()
            assert window.meetings_library_widget is library_window
            assert library_window.refresh.call_count == 3
            window.close()

    def test_real_meetings_window_survives_close_and_is_reused(
        self, qtbot, transcription_service
    ):
        application = QApplication.instance()
        assert application is not None
        meeting_service = Mock(spec=MeetingLibraryService)
        meeting_service.list_meetings.return_value = ()

        with (
            patch(
                "buzz.widgets.application.setup_app_db",
                side_effect=AssertionError("real app database must not be opened"),
            ) as setup_app_db,
            patch(
                "buzz.widgets.application.Posthog",
                side_effect=AssertionError("telemetry must not be initialized"),
            ) as posthog,
        ):
            window = MainWindow(transcription_service, meeting_service)
            qtbot.add_widget(window)

            window.on_meetings_action_triggered()

            widget = window.meetings_library_widget
            assert isinstance(widget, MeetingsLibraryWidget)
            assert meeting_service.list_meetings.call_count == 1
            assert widget.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) is False
            original_identity = widget

            widget.close()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QApplication.processEvents()

            assert not sip.isdeleted(widget)
            assert widget.table_model.rowCount() == 0

            window.on_meetings_action_triggered()

            assert window.meetings_library_widget is original_identity
            assert meeting_service.list_meetings.call_count == 2
            assert not sip.isdeleted(widget)
            assert widget.table_model.rowCount() == 0
            assert QApplication.instance() is application
            setup_app_db.assert_not_called()
            posthog.assert_not_called()
            window.close()

    def test_meetings_library_does_not_replace_legacy_central_widget(
        self, qtbot, transcription_service
    ):
        window = MainWindow(transcription_service, fake_meeting_library_service)
        qtbot.add_widget(window)
        assert window.centralWidget() is window.table_widget
        assert isinstance(window.centralWidget(), TranscriptionTasksTableWidget)
        window.close()

    def test_meeting_library_uuid_opens_and_reuses_one_detail_window(
        self, qtbot, transcription_service
    ):
        detail_window = Mock()
        first = UUID(int=1)
        second = UUID(int=2)
        with patch(
            "buzz.widgets.main_window.MeetingDetailWidget",
            return_value=detail_window,
        ) as detail_widget_type:
            window = MainWindow(transcription_service, fake_meeting_library_service)
            qtbot.add_widget(window)

            window.on_meeting_open_requested(first)
            window.on_meeting_open_requested(second)

        detail_widget_type.assert_called_once_with(
            detail_service=fake_meeting_detail_service,
            speaker_review_service=fake_speaker_review_service,
            final_transcription=None,
            meeting_notes=None,
            preview_player_factory=fake_preview_player_factory,
            parent=window,
            flags=Qt.WindowType.Window,
        )
        assert window.meeting_detail_widget is detail_window
        assert detail_window.open_meeting.call_args_list == [call(first), call(second)]
        assert detail_window.show.call_count == 2
        assert detail_window.raise_.call_count == 2
        assert detail_window.activateWindow.call_count == 2
        window.close()

    def test_real_meeting_detail_widget_close_reopen_keeps_same_qt_object(
        self, qtbot, transcription_service
    ):
        detail_service = Mock(spec=MeetingDetailService)
        detail_service.load.side_effect = MeetingDetailNotFoundError("missing")
        review_service = Mock(spec=MeetingSpeakerReviewService)
        window = ProductionMainWindow(
            transcription_service,
            fake_meeting_library_service,
            detail_service,
            review_service,
            Mock(),
        )
        qtbot.add_widget(window)
        meeting_id = UUID(int=3)

        window.on_meeting_open_requested(meeting_id)
        detail = window.meeting_detail_widget
        assert detail is not None
        assert not detail.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        detail.close()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()
        assert not sip.isdeleted(detail)

        window.on_meeting_open_requested(UUID(int=4))
        assert window.meeting_detail_widget is detail
        assert not sip.isdeleted(detail)
        window.close()

    def test_should_set_window_title_and_icon(self, qtbot, transcription_service):
        window = MainWindow(transcription_service, fake_meeting_library_service)
        qtbot.add_widget(window)
        assert window.windowTitle() == "Buzz"
        assert window.windowIcon().pixmap(QSize(64, 64)).isNull() is False
        window.close()

    def test_should_run_file_transcription_task(
        self, qtbot: QtBot, transcription_service
    ):
        window = MainWindow(transcription_service, fake_meeting_library_service)

        self._import_file_and_start_transcription(window)

        open_transcript_action = self._get_toolbar_action(window, _("Open Transcript"))
        assert open_transcript_action.isEnabled() is False

        table_widget = self._get_tasks_table(window)
        qtbot.wait_until(
            self._get_assert_task_status_callback(table_widget, 0, "completed"),
            timeout=2 * 60 * 1000,
        )

        table_widget.setCurrentIndex(table_widget.model().index(0, 0))
        assert open_transcript_action.isEnabled()
        window.close()

    @staticmethod
    def _get_tasks_table(window: MainWindow) -> QTableView:
        return window.findChild(QTableView)

    def test_should_run_url_import_file_transcription_task(
        self, qtbot: QtBot, db, transcription_service, monkeypatch, tmp_path
    ):
        source_url = (
            "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3"
        )

        class FakeYoutubeDL:
            extract_calls = []
            download_calls = []

            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def extract_info(self, requested_url, download):
                type(self).extract_calls.append((requested_url, download))
                if requested_url != source_url:
                    raise ValueError(f"unexpected URL: {requested_url}")
                return {"title": "whisper-french.mp3"}

            @staticmethod
            def sanitize_info(info):
                return info

            def download(self, requested_urls):
                type(self).download_calls.append(tuple(requested_urls))
                if requested_urls != [source_url]:
                    raise ValueError(f"unexpected URLs: {requested_urls}")
                shutil.copyfile(
                    get_test_asset("whisper-french.mp3"), self.options["outtmpl"]
                )
                return 0

        monkeypatch.setattr(
            "buzz.transcriber.file_transcriber.YoutubeDL", FakeYoutubeDL
        )
        monkeypatch.setattr(
            "buzz.file_transcriber_queue_worker.WhisperFileTranscriber",
            _LocalArtifactWhisperFileTranscriber,
        )

        local_model_path = tmp_path / "local-test-model.pt"
        local_model_path.write_bytes(b"local test model")
        model = _LocalModel(str(local_model_path))
        preferences = FileTranscriptionPreferences(
            language=None,
            task=Task.TRANSCRIBE,
            model=model,
            word_level_timings=False,
            extract_speech=False,
            initial_prompt="",
            enable_llm_translation=False,
            llm_prompt="",
            llm_model="",
            output_formats={OutputFormat.TXT},
        )
        monkeypatch.setattr(
            FileTranscriberWidget,
            "load_preferences",
            lambda _self: preferences,
        )
        _LocalArtifactWhisperFileTranscriber.seen_tasks = []

        window = MainWindow(transcription_service, fake_meeting_library_service)
        qtbot.add_widget(window)

        with (
            patch(
                "buzz.widgets.import_url_dialog.ImportURLDialog.prompt"
            ) as prompt_mock,
            patch(
                "buzz.widgets.main_window.QFileDialog.getOpenFileNames",
                side_effect=AssertionError("file import dialog must not open"),
            ),
        ):
            prompt_mock.return_value = source_url
            window.menu_bar.import_url_action.trigger()

        file_transcriber_widget: FileTranscriberWidget = window.findChild(
            FileTranscriberWidget
        )
        run_button: QPushButton = file_transcriber_widget.findChild(QPushButton)
        run_button.click()

        table_widget = self._get_tasks_table(window)
        qtbot.wait_until(
            self._get_assert_task_status_callback(table_widget, 0, "completed"),
            timeout=2 * 60 * 1000,
        )

        assert FakeYoutubeDL.extract_calls == [
            (
                "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3",
                False,
            )
        ]
        assert FakeYoutubeDL.download_calls == [
            (
                "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3",
            )
        ]
        assert len(_LocalArtifactWhisperFileTranscriber.seen_tasks) == 1
        task = _LocalArtifactWhisperFileTranscriber.seen_tasks[0]
        assert task.url == (
            "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3"
        )
        assert task.source == FileTranscriptionTask.Source.URL_IMPORT
        assert os.path.isfile(task.file_path)
        assert os.path.getsize(task.file_path) > 0

        window.close()

    @pytest.mark.timeout(300)
    def test_should_run_and_cancel_transcription_task(
        self, qtbot, db, transcription_service
    ):
        window = MainWindow(transcription_service, fake_meeting_library_service)
        qtbot.add_widget(window)

        self._import_file_and_start_transcription(window, long_audio=True)

        table_widget = self._get_tasks_table(window)

        try:
            qtbot.wait_until(
                self._get_assert_task_status_callback(table_widget, 0, "in_progress"),
                timeout=60 * 1000,
            )
        except Exception:
            logging.error("Task never reached 'in_progress' status")
            assert False, "Task did not start as expected"

        logging.debug("Will cancel transcription task")

        table_widget.selectRow(0)

        # Force immediate processing of pending events before triggering cancellation
        qtbot.wait(100)

        window.toolbar.stop_transcription_action.trigger()

        # Give some time for the cancellation to be processed
        qtbot.wait(500)

        logging.debug("Will wait for task to reach 'canceled' status")

        try:
            qtbot.wait_until(
                self._get_assert_task_status_callback(table_widget, 0, "canceled"),
                timeout=30 * 1000,
            )
        except Exception:
            # On Windows, the cancellation might be slower, check final state
            final_status = self._get_status(table_widget, 0)
            logging.error(f"Task status after timeout: {final_status}")
            if "canceled" not in final_status.lower():
                assert (
                    False
                ), f"Task did not cancel as expected. Final status: {final_status}"

        logging.debug("Task canceled")

        qtbot.wait(200)

        table_widget.selectRow(0)
        assert window.toolbar.stop_transcription_action.isEnabled() is False
        assert window.toolbar.open_transcript_action.isEnabled() is False

        window.close()

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_load_tasks_from_cache(
        self, qtbot, transcription_dao, transcription_segment_dao, monkeypatch
    ):
        # Mock the queue worker to prevent it from processing tasks
        mock_queue_worker = Mock()
        mock_queue_worker.task_started = Mock()
        mock_queue_worker.task_progress = Mock()
        mock_queue_worker.task_download_progress = Mock()
        mock_queue_worker.task_error = Mock()
        mock_queue_worker.task_completed = Mock()
        mock_queue_worker.completed = Mock()
        mock_queue_worker.cancel_task = Mock()
        mock_queue_worker.add_task = Mock()
        mock_queue_worker.stop = Mock()

        monkeypatch.setattr(
            "buzz.widgets.main_window.FileTranscriberQueueWorker",
            Mock(return_value=mock_queue_worker),
        )

        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao),
            fake_meeting_library_service,
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)
        assert table_widget.model().rowCount() == 3

        # Get all statuses and verify they match expected values
        statuses = [self._get_status(table_widget, i) for i in range(3)]
        expected_statuses = {"completed", "canceled", "failed"}
        assert (
            set(statuses) == expected_statuses
        ), f"Expected {expected_statuses}, got {statuses}"

        # Test that completed transcriptions enable the open action, others don't
        for i in range(3):
            table_widget.selectRow(i)
            status = self._get_status(table_widget, i)
            if status == "completed":
                assert window.toolbar.open_transcript_action.isEnabled()
            else:
                assert window.toolbar.open_transcript_action.isEnabled() is False
        window.close()

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_clear_history_with_rows_selected(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao),
            fake_meeting_library_service,
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)
        table_widget.selectAll()

        with patch("PyQt6.QtWidgets.QMessageBox.exec") as question_message_box_mock:
            question_message_box_mock.return_value = QMessageBox.StandardButton.Yes
            window.toolbar.clear_history_action.trigger()

        assert table_widget.model().rowCount() == 0
        window.close()

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_have_clear_history_action_disabled_with_no_rows_selected(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao),
            fake_meeting_library_service,
        )
        qtbot.add_widget(window)

        assert window.toolbar.clear_history_action.isEnabled() is False
        window.close()

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_open_transcription_viewer_when_menu_action_is_clicked(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao),
            fake_meeting_library_service,
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)

        # Find and select the completed transcription row
        completed_row = None
        for i in range(table_widget.model().rowCount()):
            if self._get_status(table_widget, i) == "completed":
                completed_row = i
                break

        assert completed_row is not None, "No completed transcription found"
        table_widget.selectRow(completed_row)

        window.toolbar.open_transcript_action.trigger()

        assert window.transcription_viewer_widget is not None

        window.close()

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_open_transcription_viewer_when_return_clicked(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao),
            fake_meeting_library_service,
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)

        # Find and select the completed transcription row
        completed_row = None
        for i in range(table_widget.model().rowCount()):
            if self._get_status(table_widget, i) == "completed":
                completed_row = i
                break

        assert completed_row is not None, "No completed transcription found"
        table_widget.selectRow(completed_row)

        table_widget.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Return,
                Qt.KeyboardModifier.NoModifier,
                "\r",
            )
        )

        assert window.transcription_viewer_widget is not None

        window.close()

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_have_open_transcript_action_disabled_with_no_rows_selected(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao),
            fake_meeting_library_service,
        )
        qtbot.add_widget(window)

        assert window.toolbar.open_transcript_action.isEnabled() is False
        window.close()

    def test_import_folder_opens_file_transcriber_with_supported_files(
        self, qtbot, transcription_service
    ):
        window = MainWindow(transcription_service, fake_meeting_library_service)
        qtbot.add_widget(window)

        with tempfile.TemporaryDirectory() as folder:
            # Create supported and unsupported files
            supported = ["audio.mp3", "video.mp4", "clip.wav"]
            unsupported = ["document.txt", "image.png"]
            subdir = os.path.join(folder, "sub")
            os.makedirs(subdir)
            nested = "nested.flac"

            for name in supported + unsupported:
                open(os.path.join(folder, name), "w").close()
            open(os.path.join(subdir, nested), "w").close()

            with patch(
                "PyQt6.QtWidgets.QFileDialog.getExistingDirectory"
            ) as mock_dir, patch.object(
                window, "open_file_transcriber_widget"
            ) as mock_open:
                mock_dir.return_value = folder
                window.on_import_folder_action_triggered()

            collected = mock_open.call_args[0][0]
            collected_names = {os.path.basename(p) for p in collected}
            assert collected_names == {
                "audio.mp3",
                "video.mp4",
                "clip.wav",
                "nested.flac",
            }

        window.close()

    def test_import_folder_does_nothing_when_cancelled(
        self, qtbot, transcription_service
    ):
        window = MainWindow(transcription_service, fake_meeting_library_service)
        qtbot.add_widget(window)

        with patch(
            "PyQt6.QtWidgets.QFileDialog.getExistingDirectory"
        ) as mock_dir, patch.object(
            window, "open_file_transcriber_widget"
        ) as mock_open:
            mock_dir.return_value = ""
            window.on_import_folder_action_triggered()

        mock_open.assert_not_called()
        window.close()

    def test_import_folder_does_nothing_when_no_supported_files(
        self, qtbot, transcription_service
    ):
        window = MainWindow(transcription_service, fake_meeting_library_service)
        qtbot.add_widget(window)

        with tempfile.TemporaryDirectory() as folder:
            open(os.path.join(folder, "readme.txt"), "w").close()
            open(os.path.join(folder, "image.jpg"), "w").close()

            with patch(
                "PyQt6.QtWidgets.QFileDialog.getExistingDirectory"
            ) as mock_dir, patch.object(
                window, "open_file_transcriber_widget"
            ) as mock_open:
                mock_dir.return_value = folder
                window.on_import_folder_action_triggered()

        mock_open.assert_not_called()
        window.close()

    def test_remembers_last_import_folder_for_file_dialog(
        self, qtbot, transcription_service
    ):
        from buzz.settings.settings import Settings

        window = MainWindow(transcription_service, fake_meeting_library_service)
        qtbot.add_widget(window)

        with tempfile.TemporaryDirectory() as folder:
            file_path = os.path.join(folder, "audio.mp3")
            open(file_path, "w").close()

            with patch(
                "PyQt6.QtWidgets.QFileDialog.getOpenFileNames"
            ) as mock_dialog, patch.object(window, "open_file_transcriber_widget"):
                mock_dialog.return_value = ([file_path], "")
                window.on_new_transcription_action_triggered()

            # The selected file's folder should be persisted
            assert window.settings.value(
                Settings.Key.LAST_IMPORT_FOLDER, ""
            ) == os.path.dirname(file_path)

            # On the next open, the dialog should be pre-pointed at that folder
            with patch(
                "PyQt6.QtWidgets.QFileDialog.getOpenFileNames"
            ) as mock_dialog, patch.object(window, "open_file_transcriber_widget"):
                mock_dialog.return_value = ([], "")
                window.on_new_transcription_action_triggered()
                assert mock_dialog.call_args[0][2] == os.path.dirname(file_path)

        window.settings.set_value(Settings.Key.LAST_IMPORT_FOLDER, "")
        window.close()

    def test_remembers_last_import_folder_for_folder_dialog(
        self, qtbot, transcription_service
    ):
        from buzz.settings.settings import Settings

        window = MainWindow(transcription_service, fake_meeting_library_service)
        qtbot.add_widget(window)

        with tempfile.TemporaryDirectory() as folder:
            open(os.path.join(folder, "audio.mp3"), "w").close()

            with patch(
                "PyQt6.QtWidgets.QFileDialog.getExistingDirectory"
            ) as mock_dir, patch.object(window, "open_file_transcriber_widget"):
                mock_dir.return_value = folder
                window.on_import_folder_action_triggered()

            assert window.settings.value(Settings.Key.LAST_IMPORT_FOLDER, "") == folder

            # The next folder dialog should start at the remembered folder
            with patch(
                "PyQt6.QtWidgets.QFileDialog.getExistingDirectory"
            ) as mock_dir, patch.object(window, "open_file_transcriber_widget"):
                mock_dir.return_value = ""
                window.on_import_folder_action_triggered()
                assert mock_dir.call_args[0][2] == folder

        window.settings.set_value(Settings.Key.LAST_IMPORT_FOLDER, "")
        window.close()

    @staticmethod
    def _import_file_and_start_transcription(
        window: MainWindow, long_audio: bool = False
    ):
        default_prefs = FileTranscriptionPreferences(
            language=None,
            task=Task.TRANSCRIBE,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY,
            ),
            word_level_timings=False,
            extract_speech=False,
            initial_prompt="",
            enable_llm_translation=False,
            llm_prompt="",
            llm_model="",
            output_formats={OutputFormat.TXT},
        )

        with patch(
            "PyQt6.QtWidgets.QFileDialog.getOpenFileNames"
        ) as open_file_names_mock, patch.object(
            FileTranscriberWidget, "load_preferences", return_value=default_prefs
        ):
            open_file_names_mock.return_value = (
                [
                    get_test_asset(
                        "audio-long.mp3" if long_audio else "whisper-french.mp3"
                    )
                ],
                "",
            )
            new_transcription_action = TestMainWindow._get_toolbar_action(
                window, _("New File Transcription")
            )
            new_transcription_action.trigger()

        file_transcriber_widget: FileTranscriberWidget = window.findChild(
            FileTranscriberWidget
        )
        run_button: QPushButton = file_transcriber_widget.findChild(QPushButton)
        run_button.click()

    @staticmethod
    def _get_assert_task_status_callback(
        table_widget: QTableView,
        row_index: int,
        expected_status: str,
    ):
        def assert_task_status():
            assert table_widget.model().rowCount() > 0
            assert expected_status in TestMainWindow._get_status(
                table_widget, row_index
            )

        return assert_task_status

    @staticmethod
    def _get_status(table_widget: QTableView, row_index: int):
        return table_widget.model().index(row_index, 9).data()

    @staticmethod
    def _get_toolbar_action(window: MainWindow, text: str):
        toolbar: QToolBar = window.findChild(QToolBar)
        return [action for action in toolbar.actions() if action.text() == text][0]
