import os
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QKeyEvent, QAction
from PyQt6.QtSql import QSqlDatabase
from PyQt6.QtWidgets import (
    QTableWidget,
    QMessageBox,
    QPushButton,
    QToolBar,
    QMenuBar,
    QTableView,
)
from pytestqt.qtbot import QtBot

from buzz.db.dao.transcription_dao import TranscriptionDAO
from buzz.db.dao.transcription_segment_dao import TranscriptionSegmentDAO
from buzz.db.db import setup_test_db
from buzz.db.service.transcription_service import TranscriptionService
from buzz.transcriber.transcriber import (
    FileTranscriptionTask,
    TranscriptionOptions,
    FileTranscriptionOptions,
)
from buzz.widgets.main_window import MainWindow
from buzz.widgets.transcriber.file_transcriber_widget import FileTranscriberWidget
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)

mock_tasks = [
    FileTranscriptionTask(
        file_path="",
        transcription_options=TranscriptionOptions(),
        file_transcription_options=FileTranscriptionOptions(file_paths=[]),
        model_path="",
        status=FileTranscriptionTask.Status.COMPLETED,
    ),
    FileTranscriptionTask(
        file_path="",
        transcription_options=TranscriptionOptions(),
        file_transcription_options=FileTranscriptionOptions(file_paths=[]),
        model_path="",
        status=FileTranscriptionTask.Status.CANCELED,
    ),
    FileTranscriptionTask(
        file_path="",
        transcription_options=TranscriptionOptions(),
        file_transcription_options=FileTranscriptionOptions(file_paths=[]),
        model_path="",
        status=FileTranscriptionTask.Status.FAILED,
        error="Error",
    ),
]


def get_test_asset(filename: str):
    return os.path.join(os.path.dirname(__file__), "../../testdata/", filename)


class TestMainWindow:
    def test_should_set_window_title_and_icon(self, qtbot):
        window = MainWindow()
        qtbot.add_widget(window)
        assert window.windowTitle() == "Buzz"
        assert window.windowIcon().pixmap(QSize(64, 64)).isNull() is False
        window.close()

    def test_should_run_file_transcription_task(
        self, qtbot: QtBot, transcription_service
    ):
        window = MainWindow(transcription_service)

        self.import_file_and_start_transcription(window)

        open_transcript_action = self._get_toolbar_action(window, "Open Transcript")
        assert open_transcript_action.isEnabled() is False

        table_widget = self._get_tasks_table(window)
        qtbot.wait_until(
            self.get_assert_task_status_callback(table_widget, 0, "completed"),
            timeout=2 * 60 * 1000,
        )

        table_widget.setCurrentIndex(table_widget.model().index(0, 0))
        assert open_transcript_action.isEnabled()
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
        ) as prompt_mock:
            prompt_mock.return_value = "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3"
            import_url_action.trigger()

        file_transcriber_widget: FileTranscriberWidget = window.findChild(
            FileTranscriberWidget
        )
        run_button: QPushButton = file_transcriber_widget.findChild(QPushButton)
        run_button.click()

        table_widget = self._get_tasks_table(window)
        qtbot.wait_until(
            self.get_assert_task_status_callback(table_widget, 0, "completed"),
            timeout=2 * 60 * 1000,
        )

        window.close()

    def test_should_run_and_cancel_transcription_task(
        self, qtbot, db, transcription_service
    ):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)

        self.import_file_and_start_transcription(window, long_audio=True)

        table_widget = self._get_tasks_table(window)

        qtbot.wait_until(
            self.get_assert_task_status_callback(table_widget, 0, "in_progress"),
            timeout=2 * 60 * 1000,
        )

        # Stop task in progress
        table_widget.selectRow(0)
        window.toolbar.stop_transcription_action.trigger()

        qtbot.wait_until(
            self.get_assert_task_status_callback(table_widget, 0, "canceled"),
            timeout=60 * 1000,
        )

        # table_widget.selectRow(0)
        # assert window.toolbar.stop_transcription_action.isEnabled() is False
        # assert window.toolbar.open_transcript_action.isEnabled() is False
        #
        window.close()

    @pytest.mark.parametrize("tasks_cache", [mock_tasks], indirect=True)
    def test_should_load_tasks_from_cache(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        table_widget: QTableWidget = self._get_tasks_table(window)
        assert table_widget.rowCount() == 3

        assert table_widget.item(0, 4).text() == "Completed"
        table_widget.selectRow(0)
        assert window.toolbar.open_transcript_action.isEnabled()

        assert table_widget.item(1, 4).text() == "Canceled"
        table_widget.selectRow(1)
        assert window.toolbar.open_transcript_action.isEnabled() is False

        assert table_widget.item(2, 4).text() == "Failed (Error)"
        table_widget.selectRow(2)
        assert window.toolbar.open_transcript_action.isEnabled() is False
        window.close()

    @pytest.mark.parametrize("tasks_cache", [mock_tasks], indirect=True)
    def test_should_clear_history_with_rows_selected(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)

        table_widget: QTableWidget = self._get_tasks_table(window)
        table_widget.selectAll()

        with patch("PyQt6.QtWidgets.QMessageBox.question") as question_message_box_mock:
            question_message_box_mock.return_value = QMessageBox.StandardButton.Yes
            window.toolbar.clear_history_action.trigger()

        assert table_widget.rowCount() == 0
        window.close()

    @pytest.mark.parametrize("tasks_cache", [mock_tasks], indirect=True)
    def test_should_have_clear_history_action_disabled_with_no_rows_selected(
        self, qtbot, tasks_cache
    ):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        assert window.toolbar.clear_history_action.isEnabled() is False
        window.close()

    @pytest.mark.parametrize("tasks_cache", [mock_tasks], indirect=True)
    def test_should_open_transcription_viewer_when_menu_action_is_clicked(
        self, qtbot, tasks_cache, db
    ):
        window = MainWindow(
            transcription_dao=TranscriptionDAO(db), tasks_cache=tasks_cache
        )
        qtbot.add_widget(window)

        table_widget: QTableWidget = self._get_tasks_table(window)

        table_widget.selectRow(0)

        window.toolbar.open_transcript_action.trigger()

        transcription_viewer = window.findChild(TranscriptionViewerWidget)
        assert transcription_viewer is not None

        window.close()

    @pytest.mark.parametrize("tasks_cache", [mock_tasks], indirect=True)
    def test_should_open_transcription_viewer_when_return_clicked(
        self, qtbot, tasks_cache
    ):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        table_widget: QTableWidget = self._get_tasks_table(window)
        table_widget.selectRow(0)
        table_widget.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Return,
                Qt.KeyboardModifier.NoModifier,
                "\r",
            )
        )

        transcription_viewer = window.findChild(TranscriptionViewerWidget)
        assert transcription_viewer is not None

        window.close()

    @pytest.mark.parametrize("tasks_cache", [mock_tasks], indirect=True)
    def test_should_have_open_transcript_action_disabled_with_no_rows_selected(
        self, qtbot, tasks_cache
    ):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        assert window.toolbar.open_transcript_action.isEnabled() is False
        window.close()

    @staticmethod
    def import_file_and_start_transcription(
        window: MainWindow, long_audio: bool = False
    ):
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getOpenFileNames"
        ) as open_file_names_mock:
            open_file_names_mock.return_value = (
                [
                    get_test_asset(
                        "audio-long.mp3" if long_audio else "whisper-french.mp3"
                    )
                ],
                "",
            )
            new_transcription_action = TestMainWindow._get_toolbar_action(
                window, "New Transcription"
            )
            new_transcription_action.trigger()

        file_transcriber_widget: FileTranscriberWidget = window.findChild(
            FileTranscriberWidget
        )
        run_button: QPushButton = file_transcriber_widget.findChild(QPushButton)
        run_button.click()

    @staticmethod
    def get_assert_task_status_callback(
        table_widget: QTableView,
        row_index: int,
        expected_status: str,
    ):
        def assert_task_status():
            assert table_widget.model().rowCount() > 0
            print(table_widget.model().index(row_index, 9).data(), expected_status)
            assert expected_status in table_widget.model().index(row_index, 9).data()

        return assert_task_status

    @staticmethod
    def _get_toolbar_action(window: MainWindow, text: str):
        toolbar: QToolBar = window.findChild(QToolBar)
        return [action for action in toolbar.actions() if action.text() == text][0]


@pytest.fixture()
def db() -> QSqlDatabase:
    db = setup_test_db()
    yield db
    db.close()
    os.remove(db.databaseName())


@pytest.fixture()
def transcription_dao(db) -> TranscriptionDAO:
    return TranscriptionDAO(db)


@pytest.fixture()
def transcription_service(transcription_dao, db) -> TranscriptionService:
    return TranscriptionService(transcription_dao, TranscriptionSegmentDAO(db))
