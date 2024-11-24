import os
from typing import List
from unittest.mock import patch

import pytest
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
from buzz.widgets.main_window import MainWindow
from buzz.widgets.snap_notice import SnapNotice
from buzz.widgets.transcriber.file_transcriber_widget import FileTranscriberWidget
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)

mock_transcriptions: List[Transcription] = [
    Transcription(status="completed"),
    Transcription(status="canceled"),
    Transcription(status="failed", error_message=_("Error")),
]


def get_test_asset(filename: str):
    return os.path.join(os.path.dirname(__file__), "../../testdata/", filename)


class TestMainWindow:
    def test_should_set_window_title_and_icon(self, qtbot, transcription_service):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)
        assert window.windowTitle() == "Buzz"
        assert window.windowIcon().pixmap(QSize(64, 64)).isNull() is False
        window.close()

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
            self._get_assert_task_status_callback(table_widget, 0, "completed"),
            timeout=2 * 60 * 1000,
        )

        window.close()

    def test_should_run_and_cancel_transcription_task(
        self, qtbot, db, transcription_service
    ):
        window = MainWindow(transcription_service)
        qtbot.add_widget(window)

        self._import_file_and_start_transcription(window, long_audio=True)

        table_widget = self._get_tasks_table(window)

        qtbot.wait_until(
            self._get_assert_task_status_callback(table_widget, 0, "in_progress"),
            timeout=2 * 60 * 1000,
        )

        # Stop task in progress
        table_widget.selectRow(0)
        window.toolbar.stop_transcription_action.trigger()

        qtbot.wait_until(
            self._get_assert_task_status_callback(table_widget, 0, "canceled"),
            timeout=60 * 1000,
        )

        table_widget.selectRow(0)
        assert window.toolbar.stop_transcription_action.isEnabled() is False
        assert window.toolbar.open_transcript_action.isEnabled() is False

        window.close()

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_load_tasks_from_cache(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)
        assert table_widget.model().rowCount() == 3

        assert self._get_status(table_widget, 0) == "completed"
        table_widget.selectRow(0)
        assert window.toolbar.open_transcript_action.isEnabled()

        assert self._get_status(table_widget, 1) == "canceled"
        table_widget.selectRow(1)
        assert window.toolbar.open_transcript_action.isEnabled() is False

        assert self._get_status(table_widget, 2) == "failed"
        table_widget.selectRow(2)
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

    @pytest.mark.parametrize("transcription_dao", [mock_transcriptions], indirect=True)
    def test_should_open_transcription_viewer_when_menu_action_is_clicked(
        self, qtbot, transcription_dao, transcription_segment_dao
    ):
        window = MainWindow(
            TranscriptionService(transcription_dao, transcription_segment_dao)
        )
        qtbot.add_widget(window)

        table_widget = self._get_tasks_table(window)
        table_widget.selectRow(0)

        window.toolbar.open_transcript_action.trigger()

        transcription_viewer = window.findChild(TranscriptionViewerWidget)
        assert transcription_viewer is not None

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

    @staticmethod
    def _import_file_and_start_transcription(
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

    def test_snap_notice_dialog(self, qtbot: QtBot):
        snap_notice = SnapNotice()
        snap_notice.show()

        qtbot.wait_until(lambda: snap_notice.isVisible(), timeout=1000)

        snap_notice.close()
        assert not snap_notice.isVisible()
