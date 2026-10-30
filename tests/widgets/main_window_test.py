import logging
import os
import shutil
import tempfile
import threading
from typing import List
from unittest.mock import call, patch, Mock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QKeyEvent, QAction
from PyQt6.QtWidgets import (
    QMessageBox,
    QPushButton,
    QToolBar,
    QMenuBar,
    QTableView,
)
from pytestqt.qtbot import QtBot

from buzz.locale import _
from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import (
    FileTranscriptionOptions,
    FileTranscriptionTask,
    OutputFormat,
    Segment,
    Task,
    TranscriptionOptions,
)
from buzz.widgets.main_window import MainWindow
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import FileTranscriptionPreferences
from buzz.widgets.transcriber.file_transcriber_widget import FileTranscriberWidget

mock_transcriptions: List[Transcription] = [
    Transcription(status="completed"),
    Transcription(status="canceled"),
    Transcription(status="failed", error_message=_("Error")),
]


def get_test_asset(filename: str):
    return os.path.join(os.path.dirname(__file__), "../../testdata/", filename)


@pytest.fixture(autouse=True)
def restore_file_transcriber_preferences():
    """MainWindow uses the real app settings, and FileTranscriberWidget saves its
    preferences (e.g. the TXT export format used in these tests) on close.
    Snapshot the group and restore it so tests don't leak into user settings."""
    settings = Settings().settings
    settings.beginGroup("file_transcriber")
    snapshot = {key: settings.value(key) for key in settings.allKeys()}
    settings.endGroup()

    yield

    settings.beginGroup("file_transcriber")
    settings.remove("")
    for key, value in snapshot.items():
        settings.setValue(key, value)
    settings.endGroup()
    settings.sync()


class TestMainWindow:
    def test_should_set_window_title_and_icon(self, qtbot, transcription_service):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)
        assert window.windowTitle() == "Buzz"
        assert window.windowIcon().pixmap(QSize(64, 64)).isNull() is False
        window.close()

    def test_queue_busy_changes_are_serialized_on_gui_thread(
        self, qtbot, transcription_service
    ):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)
        window.sleep_inhibitor = Mock()

        background_emit = threading.Thread(
            target=lambda: window.transcriber_worker.queue_busy_changed.emit(False)
        )
        background_emit.start()
        background_emit.join()
        window.transcriber_worker.queue_busy_changed.emit(True)

        qtbot.wait_until(
            lambda: window.sleep_inhibitor.set_busy.call_count == 2,
            timeout=1000,
        )
        assert window.sleep_inhibitor.set_busy.call_args_list == [
            call(False),
            call(True),
        ]
        window.close()

    @staticmethod
    def _schedule_cuda_prompt(window: MainWindow):
        """Run _maybe_show_cuda_prompt as on a machine with an NVIDIA GPU and
        CPU-only torch, without touching the real CUDA_PROMPT_SHOWN setting."""
        window.settings = Mock()
        window.settings.value.return_value = False
        with patch("buzz.cuda_manager.is_nvidia_gpu_present", return_value=True), \
                patch("buzz.cuda_manager.should_offer_cuda_prompt", return_value=True), \
                patch("buzz.cuda_manager.is_cuda_torch_installed", return_value=False):
            window._maybe_show_cuda_prompt()

    def test_cuda_prompt_shows_after_delay(self, qtbot: QtBot, transcription_service):
        with patch("buzz.cuda_manager.is_nvidia_gpu_present", return_value=False):
            window = MainWindow(transcription_service)
        qtbot.add_widget(window)

        with patch("buzz.widgets.cuda_installer_widget.CudaInstallerDialog") as dialog:
            self._schedule_cuda_prompt(window)
            qtbot.waitUntil(lambda: dialog.called, timeout=2000)

        dialog.assert_called_once_with(window)

    def test_cuda_prompt_does_not_fire_after_window_is_deleted(
        self, qtbot: QtBot, transcription_service
    ):
        with patch("buzz.cuda_manager.is_nvidia_gpu_present", return_value=False):
            window = MainWindow(transcription_service)

        with patch("buzz.widgets.cuda_installer_widget.CudaInstallerDialog") as dialog:
            self._schedule_cuda_prompt(window)
            # The window goes away before the 500 ms prompt delay is up.
            window.close()
            sip.delete(window)
            qtbot.wait(800)

        dialog.assert_not_called()

    def test_should_run_file_transcription_task(
        self, qtbot: QtBot, transcription_service
    ):
        window = MainWindow(transcription_service)

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
    def _folder_watch_task() -> FileTranscriptionTask:
        file_path = get_test_asset("whisper-french.mp3")
        return FileTranscriptionTask(
            file_path=file_path,
            original_file_path=file_path,
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(
                file_paths=[file_path]
            ),
            model_path="",
            source=FileTranscriptionTask.Source.FOLDER_WATCH,
        )

    def test_folder_watch_task_is_listed_at_once_and_transcribed_once_settled(
        self, qtbot: QtBot, transcription_service
    ):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)
        task = self._folder_watch_task()

        with patch.object(window.transcriber_worker, "add_task") as add_task:
            window.on_folder_watch_task_found(task)
            assert transcription_service.is_transcription_queued(task.uid)
            add_task.assert_not_called()

            window.on_folder_watch_task_settled(task)
            add_task.assert_called_once_with(task)

        window.close()

    def test_folder_watch_task_stopped_before_it_settles_is_not_transcribed(
        self, qtbot: QtBot, transcription_service
    ):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)
        task = self._folder_watch_task()

        with patch.object(window.transcriber_worker, "add_task") as add_task:
            window.on_folder_watch_task_found(task)
            transcription_service.update_transcription_as_canceled(task.uid)

            window.on_folder_watch_task_settled(task)
            add_task.assert_not_called()

        window.close()

    def test_folder_watch_task_deleted_before_it_settles_is_not_transcribed(
        self, qtbot: QtBot, transcription_service
    ):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)
        task = self._folder_watch_task()

        with patch.object(window.transcriber_worker, "add_task") as add_task:
            window.on_folder_watch_task_found(task)

            table_widget = self._get_tasks_table(window)
            table_widget.selectRow(0)
            self._press_delete(table_widget)
            assert table_widget.model().rowCount() == 0

            window.on_folder_watch_task_settled(task)
            add_task.assert_not_called()

        window.close()

    def test_folder_watch_task_discarded_before_it_settles_is_canceled(
        self, qtbot: QtBot, transcription_service
    ):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)
        task = self._folder_watch_task()

        window.on_folder_watch_task_found(task)
        window.on_folder_watch_task_discarded(task)

        transcription = transcription_service.transcription_dao.find_by_id(
            str(task.uid)
        )
        assert transcription.status == FileTranscriptionTask.Status.CANCELED.value
        window.close()

    @staticmethod
    def _get_tasks_table(window: MainWindow) -> QTableView:
        return window.findChild(QTableView)

    def test_should_run_url_import_file_transcription_task(
        self, qtbot: QtBot, db, transcription_service
    ):
        window = MainWindow(transcription_service)
        menu: QMenuBar = window.menuBar()
        file_action = menu.actions()[0]
        import_url_action: QAction = file_action.menu().actions()[1]

        with patch(
            "buzz.widgets.import_url_dialog.ImportURLDialog.prompt"
        ) as prompt_mock, patch.object(
            FileTranscriberWidget,
            "load_preferences",
            return_value=self._default_file_transcription_preferences(),
        ):
            prompt_mock.return_value = "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3"
            import_url_action.trigger()

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

        window.close()

    @pytest.mark.timeout(300)
    def test_should_run_and_cancel_transcription_task(
        self, qtbot, db, transcription_service
    ):
        window = MainWindow(transcription_service)
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
                assert False, f"Task did not cancel as expected. Final status: {final_status}"

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
        
        monkeypatch.setattr("buzz.widgets.main_window.FileTranscriberQueueWorker", Mock(return_value=mock_queue_worker))
        
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)
        assert table_widget.model().rowCount() == 3

        # Get all statuses and verify they match expected values
        statuses = [self._get_status(table_widget, i) for i in range(3)]
        expected_statuses = {"completed", "canceled", "failed"}
        assert set(statuses) == expected_statuses, f"Expected {expected_statuses}, got {statuses}"

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
            TranscriptionService(transcription_dao, transcription_segment_dao)
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
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        assert window.toolbar.clear_history_action.isEnabled() is False
        window.close()

    @staticmethod
    def _press_delete(
        table_widget: QTableView, reply=QMessageBox.StandardButton.Yes
    ) -> Mock:
        with patch("PyQt6.QtWidgets.QMessageBox.exec") as question_message_box_mock:
            question_message_box_mock.return_value = reply
            table_widget.keyPressEvent(
                QKeyEvent(
                    QKeyEvent.Type.KeyPress,
                    Qt.Key.Key_Delete,
                    Qt.KeyboardModifier.NoModifier,
                )
            )
        return question_message_box_mock

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_clear_history_when_delete_pressed(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)
        table_widget.selectAll()

        with patch.object(window.transcriber_worker, "cancel_task") as cancel_task:
            question_message_box_mock = self._press_delete(table_widget)

        question_message_box_mock.assert_called_once()
        cancel_task.assert_not_called()
        assert table_widget.model().rowCount() == 0
        window.close()

    @pytest.mark.parametrize(
        "transcription_dao",
        [[Transcription(status="queued")], [Transcription(status="in_progress")]],
        ids=["queued", "in_progress"],
        indirect=True,
    )
    def test_should_cancel_and_delete_active_task_when_delete_pressed(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)
        table_widget.selectRow(0)
        transcription = table_widget.selected_transcriptions()[0]

        with patch.object(window.transcriber_worker, "cancel_task") as cancel_task:
            question_message_box_mock = self._press_delete(table_widget)

        question_message_box_mock.assert_called_once()
        cancel_task.assert_called_once_with(transcription.id_as_uuid)
        assert table_widget.model().rowCount() == 0
        window.close()

    @pytest.mark.parametrize(
        "transcription_dao", [[Transcription(status="in_progress")]], indirect=True
    )
    def test_should_keep_active_task_when_delete_is_not_confirmed(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)
        table_widget.selectRow(0)

        with patch.object(window.transcriber_worker, "cancel_task") as cancel_task:
            self._press_delete(table_widget, reply=QMessageBox.StandardButton.No)

        cancel_task.assert_not_called()
        assert table_widget.model().rowCount() == 1
        window.close()

    @pytest.mark.parametrize(
        "transcription_dao",
        [
            [
                Transcription(status="completed"),
                Transcription(status="queued"),
                Transcription(status="in_progress"),
                Transcription(status="failed", error_message=_("Error")),
            ]
        ],
        indirect=True,
    )
    def test_should_cancel_only_active_tasks_when_delete_pressed(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)
        table_widget.selectAll()
        active_ids = {
            transcription.id_as_uuid
            for transcription in table_widget.selected_transcriptions()
            if transcription.status in ("queued", "in_progress")
        }

        with patch.object(window.transcriber_worker, "cancel_task") as cancel_task:
            self._press_delete(table_widget)

        assert cancel_task.call_count == 2
        assert {
            canceled.args[0] for canceled in cancel_task.call_args_list
        } == active_ids
        assert table_widget.model().rowCount() == 0
        window.close()

    @pytest.mark.parametrize(
        "transcription_dao", [[Transcription(status="in_progress")]], indirect=True
    )
    def test_should_drop_completion_of_running_task_deleted_with_delete_key(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)
        table_widget.selectRow(0)
        transcription = table_widget.selected_transcriptions()[0]

        # The queue worker is transcribing this task
        window.transcriber_worker.current.task = FileTranscriptionTask(
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(),
            model_path="",
            uid=transcription.id_as_uuid,
        )

        self._press_delete(table_widget)

        # Then the transcriber finishes it. Saving its segments would fail the
        # foreign key of the deleted row, and PyQt aborts on an exception
        # raised in a slot. Without a post-processing plugin the segments are
        # saved in the slot itself, whatever the local settings enable.
        with patch.object(
            window.plugin_manager, "has_enabled_post_hooks", return_value=False
        ), qtbot.capture_exceptions() as exceptions:
            window.transcriber_worker.on_task_completed(
                [Segment(start=0, end=1000, text="Bonjour")]
            )

        assert exceptions == []
        assert transcription_dao.find_by_id(transcription.id) is None
        window.close()

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_open_transcription_viewer_when_menu_action_is_clicked(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
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
            TranscriptionService(transcription_dao, transcription_segment_dao)
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

    def _open_completed_transcription_viewer(self, window: MainWindow):
        table_widget = self._get_tasks_table(window)
        for i in range(table_widget.model().rowCount()):
            if self._get_status(table_widget, i) == "completed":
                table_widget.selectRow(i)
                break
        window.toolbar.open_transcript_action.trigger()
        return window.transcription_viewer_widget

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_delete_transcription_viewer_when_closed(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        viewer = self._open_completed_transcription_viewer(window)
        viewer.close()

        # A closed viewer left alive keeps its media player around until
        # exit, where PyQt's cleanup segfaults on it
        qtbot.waitUntil(lambda: sip.isdeleted(viewer))

        window.close()

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_delete_open_transcription_viewers_when_closed(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        first_viewer = self._open_completed_transcription_viewer(window)
        second_viewer = self._open_completed_transcription_viewer(window)

        window.close()

        assert sip.isdeleted(first_viewer)
        assert sip.isdeleted(second_viewer)
        assert window.transcription_viewer_widget is None

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_have_open_transcript_action_disabled_with_no_rows_selected(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        assert window.toolbar.open_transcript_action.isEnabled() is False
        window.close()

    def test_import_folder_opens_file_transcriber_with_supported_files(
        self, qtbot, transcription_service
    ):
        window = MainWindow(transcription_service)
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

            with patch("PyQt6.QtWidgets.QFileDialog.getExistingDirectory") as mock_dir, \
                 patch.object(window, "open_file_transcriber_widget") as mock_open:
                mock_dir.return_value = folder
                window.on_import_folder_action_triggered()

            collected = mock_open.call_args[0][0]
            collected_names = {os.path.basename(p) for p in collected}
            assert collected_names == {"audio.mp3", "video.mp4", "clip.wav", "nested.flac"}

        window.close()

    def test_import_folder_does_nothing_when_cancelled(
        self, qtbot, transcription_service
    ):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)

        with patch("PyQt6.QtWidgets.QFileDialog.getExistingDirectory") as mock_dir, \
             patch.object(window, "open_file_transcriber_widget") as mock_open:
            mock_dir.return_value = ""
            window.on_import_folder_action_triggered()

        mock_open.assert_not_called()
        window.close()

    def test_import_folder_does_nothing_when_no_supported_files(
        self, qtbot, transcription_service
    ):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)

        with tempfile.TemporaryDirectory() as folder:
            open(os.path.join(folder, "readme.txt"), "w").close()
            open(os.path.join(folder, "image.jpg"), "w").close()

            with patch("PyQt6.QtWidgets.QFileDialog.getExistingDirectory") as mock_dir, \
                 patch.object(window, "open_file_transcriber_widget") as mock_open:
                mock_dir.return_value = folder
                window.on_import_folder_action_triggered()

        mock_open.assert_not_called()
        window.close()

    def test_remembers_last_import_folder_for_file_dialog(
        self, qtbot, transcription_service
    ):
        from buzz.settings.settings import Settings

        window = MainWindow(transcription_service)
        qtbot.add_widget(window)

        with tempfile.TemporaryDirectory() as folder:
            file_path = os.path.join(folder, "audio.mp3")
            open(file_path, "w").close()

            with patch(
                "PyQt6.QtWidgets.QFileDialog.getOpenFileNames"
            ) as mock_dialog, patch.object(
                window, "open_file_transcriber_widget"
            ):
                mock_dialog.return_value = ([file_path], "")
                window.on_new_transcription_action_triggered()

            # The selected file's folder should be persisted
            assert window.settings.value(
                Settings.Key.LAST_IMPORT_FOLDER, ""
            ) == os.path.dirname(file_path)

            # On the next open, the dialog should be pre-pointed at that folder
            with patch(
                "PyQt6.QtWidgets.QFileDialog.getOpenFileNames"
            ) as mock_dialog, patch.object(
                window, "open_file_transcriber_widget"
            ):
                mock_dialog.return_value = ([], "")
                window.on_new_transcription_action_triggered()
                assert mock_dialog.call_args[0][2] == os.path.dirname(file_path)

        window.settings.set_value(Settings.Key.LAST_IMPORT_FOLDER, "")
        window.close()

    def test_remembers_last_import_folder_for_folder_dialog(
        self, qtbot, transcription_service
    ):
        from buzz.settings.settings import Settings

        window = MainWindow(transcription_service)
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
    def _default_file_transcription_preferences() -> FileTranscriptionPreferences:
        return FileTranscriptionPreferences(
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

    @staticmethod
    def _import_file_and_start_transcription(
        window: MainWindow, long_audio: bool = False
    ):
        default_prefs = TestMainWindow._default_file_transcription_preferences()

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


class TestMainWindowFolderWatch:
    def test_should_store_new_file_path_after_folder_watch_move(
        self, qtbot: QtBot, db, transcription_service, tmp_path
    ):
        """The transcription must point at the moved file, so audio still plays."""
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)

        input_directory = tmp_path / "input"
        output_directory = tmp_path / "output"
        input_directory.mkdir()
        output_directory.mkdir()

        input_path = input_directory / "whisper-french.mp3"
        shutil.copy(get_test_asset("whisper-french.mp3"), input_path)

        task = FileTranscriptionTask(
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(
                file_paths=[str(input_path)]
            ),
            model_path="",
            file_path=str(input_path),
            original_file_path=str(input_path),
            output_directory=str(output_directory),
            source=FileTranscriptionTask.Source.FOLDER_WATCH,
        )
        transcription_service.create_transcription(task)

        # The transcriber moves the file and updates the task before completing.
        moved_path = output_directory / "whisper-french.mp3"
        shutil.move(input_path, moved_path)
        task.file_path = str(moved_path)

        window.on_task_completed(task, [])

        transcription = transcription_service.transcription_dao.find_by_id(
            str(task.uid)
        )
        assert transcription.file == str(moved_path)

        window.close()


class TestMainWindowUrlImport:
    def test_should_store_downloaded_audio_not_extracted_speech(
        self, qtbot: QtBot, db, transcription_service, tmp_path
    ):
        """The speech file is deleted after completion, so the transcription
        has to keep pointing at the downloaded audio."""
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)

        downloaded_path = tmp_path / "audio.wav"
        speech_path = tmp_path / "audio_speech.mp3"
        task = FileTranscriptionTask(
            transcription_options=TranscriptionOptions(extract_speech=True),
            file_transcription_options=FileTranscriptionOptions(),
            model_path="",
            url="https://example.com/audio.mp3",
            source=FileTranscriptionTask.Source.URL_IMPORT,
        )
        transcription_service.create_transcription(task)

        # Download, then speech extraction, update the task before completing.
        task.original_file_path = str(downloaded_path)
        task.file_path = str(speech_path)

        window.on_task_completed(task, [])

        transcription = transcription_service.transcription_dao.find_by_id(
            str(task.uid)
        )
        assert transcription.file == str(downloaded_path)
        assert transcription.name == "audio"

        window.close()
