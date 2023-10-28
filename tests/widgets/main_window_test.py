import os
from typing import List
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QTableWidget, QMessageBox, QPushButton, QToolBar
from _pytest.fixtures import SubRequest
from pytestqt.qtbot import QtBot

from buzz.cache import TasksCache
from buzz.transcriber import (
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

    def test_should_run_transcription_task(self, qtbot: QtBot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)

        self._start_new_transcription(window)

        open_transcript_action = self._get_toolbar_action(window, "Open Transcript")
        assert open_transcript_action.isEnabled() is False

        table_widget: QTableWidget = window.findChild(QTableWidget)
        qtbot.wait_until(
            self._assert_task_status(table_widget, 0, "Completed"),
            timeout=2 * 60 * 1000,
        )

        table_widget.setCurrentIndex(
            table_widget.indexFromItem(table_widget.item(0, 1))
        )
        assert open_transcript_action.isEnabled()
        window.close()

    # @pytest.mark.skip(reason='Timing out or crashing')
    def test_should_run_and_cancel_transcription_task(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        self._start_new_transcription(window)

        table_widget: QTableWidget = window.findChild(QTableWidget)

        def assert_task_in_progress():
            assert table_widget.rowCount() > 0
            assert table_widget.item(0, 1).text() == "whisper-french.mp3"
            assert "In Progress" in table_widget.item(0, 2).text()

        qtbot.wait_until(assert_task_in_progress, timeout=2 * 60 * 1000)

        # Stop task in progress
        table_widget.selectRow(0)
        window.toolbar.stop_transcription_action.trigger()

        qtbot.wait_until(
            self._assert_task_status(table_widget, 0, "Canceled"), timeout=60 * 1000
        )

        table_widget.selectRow(0)
        assert window.toolbar.stop_transcription_action.isEnabled() is False
        assert window.toolbar.open_transcript_action.isEnabled() is False

        window.close()

    @pytest.mark.parametrize("tasks_cache", [mock_tasks], indirect=True)
    def test_should_load_tasks_from_cache(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        table_widget: QTableWidget = window.findChild(QTableWidget)
        assert table_widget.rowCount() == 3

        assert table_widget.item(0, 2).text() == "Completed"
        table_widget.selectRow(0)
        assert window.toolbar.open_transcript_action.isEnabled()

        assert table_widget.item(1, 2).text() == "Canceled"
        table_widget.selectRow(1)
        assert window.toolbar.open_transcript_action.isEnabled() is False

        assert table_widget.item(2, 2).text() == "Failed (Error)"
        table_widget.selectRow(2)
        assert window.toolbar.open_transcript_action.isEnabled() is False
        window.close()

    @pytest.mark.parametrize("tasks_cache", [mock_tasks], indirect=True)
    def test_should_clear_history_with_rows_selected(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)

        table_widget: QTableWidget = window.findChild(QTableWidget)
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
        self, qtbot, tasks_cache
    ):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        table_widget: QTableWidget = window.findChild(QTableWidget)

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

        table_widget: QTableWidget = window.findChild(QTableWidget)
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
    def _start_new_transcription(window: MainWindow):
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getOpenFileNames"
        ) as open_file_names_mock:
            open_file_names_mock.return_value = (
                [get_test_asset("whisper-french.mp3")],
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
    def _assert_task_status(
        table_widget: QTableWidget, row_index: int, expected_status: str
    ):
        def assert_task_canceled():
            assert table_widget.rowCount() > 0
            assert table_widget.item(row_index, 1).text() == "whisper-french.mp3"
            assert expected_status in table_widget.item(row_index, 2).text()

        return assert_task_canceled

    @staticmethod
    def _get_toolbar_action(window: MainWindow, text: str):
        toolbar: QToolBar = window.findChild(QToolBar)
        return [action for action in toolbar.actions() if action.text() == text][0]


@pytest.fixture()
def tasks_cache(tmp_path, request: SubRequest):
    cache = TasksCache(cache_dir=str(tmp_path))
    if hasattr(request, "param"):
        tasks: List[FileTranscriptionTask] = request.param
        cache.save(tasks)
    yield cache
    cache.clear()
