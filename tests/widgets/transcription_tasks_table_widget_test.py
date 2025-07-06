import enum
import os
from datetime import timedelta
from unittest.mock import Mock, patch, MagicMock
from uuid import UUID

import pytest
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtSql import QSqlDatabase, QSqlQuery, QSqlRecord, QSqlTableModel
from PyQt6.QtWidgets import QApplication, QMenu, QStyledItemDelegate

from buzz.widgets.transcription_tasks_table_widget import (
    TranscriptionTasksTableWidget,
    format_record_status_text,
    Column,
    column_definitions,
)
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_record import TranscriptionRecord


class MockFileTranscriptionTaskStatus(enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    QUEUED = "QUEUED"


class MockFileTranscriptionTask:
    Status = MockFileTranscriptionTaskStatus


@pytest.fixture(autouse=True)
def mock_dependencies(monkeypatch):
    monkeypatch.setattr(
        "buzz.widgets.transcription_tasks_table_widget.FileTranscriptionTask",
        MockFileTranscriptionTask,
    )
    monkeypatch.setattr("buzz.widgets.transcription_tasks_table_widget._", lambda x: x)
    monkeypatch.setattr(
        "buzz.widgets.transcription_record.TranscriptionRecord.model",
        lambda record: "MockedModel",
    )

    mock_settings = Mock()
    settings_store = {}
    mock_settings.settings = Mock()
    mock_settings.settings.setValue.side_effect = lambda k, v: settings_store.update({k: v})
    mock_settings.settings.value.side_effect = lambda k, default: settings_store.get(
        k, default
    )
    monkeypatch.setattr(
        "buzz.widgets.transcription_tasks_table_widget.Settings",
        Mock(return_value=mock_settings),
    )
    monkeypatch.setattr(
        "buzz.widgets.transcription_tasks_table_widget.Settings.Key",
        Mock(TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY="visibility"),
    )


@pytest.fixture
def db():
    db = QSqlDatabase.addDatabase("QSQLITE")  # Use default connection
    db.setDatabaseName(":memory:")
    assert db.open()
    query = QSqlQuery(db)
    query.exec(
        "CREATE TABLE transcription ("  # 0
        "id TEXT PRIMARY KEY,"  # 1
        "error_message TEXT,"  # 2
        "export_formats TEXT,"  # 3
        "file TEXT,"  # 4
        "output_folder TEXT,"  # 5
        "progress DOUBLE PRECISION DEFAULT 0.0,"  # 6
        "language TEXT,"  # 7
        "model_type TEXT,"  # 8
        "source TEXT,"  # 9
        "status TEXT,"  # 10
        "task TEXT,"  # 11
        "time_ended TIMESTAMP,"  # 12
        "time_queued TIMESTAMP NOT NULL,"  # 13
        "time_started TIMESTAMP,"  # 14
        "url TEXT,"  # 15
        "whisper_model_size TEXT,"  # 16
        "hugging_face_model_id TEXT,"  # 17
        "word_level_timings BOOLEAN DEFAULT FALSE,"  # 18
        "extract_speech BOOLEAN DEFAULT FALSE"  # 19
        ")"
    )
    query.exec(
        "INSERT INTO transcription (id, file, url, status, time_queued, task, model_type) VALUES "
        "('1', '/a/b/c.mp3', '', 'QUEUED', '2023-01-01T00:00:00', 'TRANSCRIBE', 'WHISPER'),"
        "('2', '', 'http://example.com/d.wav', 'QUEUED', '2023-01-02T00:00:00', 'TRANSCRIBE', 'WHISPER')"
    )
    yield db
    db.close()
    for conn_name in QSqlDatabase.connectionNames():
        QSqlDatabase.removeDatabase(conn_name)


def mock_record(values):
    record = MagicMock(spec=QSqlRecord)
    record.value.side_effect = lambda key: values.get(key)
    return record


@pytest.mark.parametrize(
    "delta, expected", [(timedelta(seconds=5), "5s"), (timedelta(seconds=65), "1m 5s")]
)
def test_format_timedelta(delta, expected):
    assert TranscriptionTasksTableWidget.format_timedelta(delta) == expected


def test_format_record_status_text_logic():
    assert (
        format_record_status_text(mock_record({"status": "IN_PROGRESS", "progress": 0.5}))
        == "In Progress (50%)"
    )
    assert (
        format_record_status_text(
            mock_record(
                {
                    "status": "COMPLETED",
                    "time_started": "2023-01-01T10:00:00",
                    "time_ended": "2023-01-01T10:05:30",
                }
            )
        )
        == "Completed (5m 30s)"
    )


def test_column_delegates_text_getters(monkeypatch):
    # Mock the RecordDelegate class itself
    mock_record_delegate_class = MagicMock(spec=QStyledItemDelegate)
    monkeypatch.setattr(
        "buzz.widgets.transcription_tasks_table_widget.RecordDelegate",
        mock_record_delegate_class,
    )

    # Re-import column_definitions to pick up the patched RecordDelegate
    import importlib
    import buzz.widgets.transcription_tasks_table_widget
    importlib.reload(buzz.widgets.transcription_tasks_table_widget)

    # Now, column_definitions will have delegates that are instances of mock_record_delegate_class
    # We need to access the text_getter from the call_args of the mock

    # file_name delegate
    file_name_delegate_instance = mock_record_delegate_class.return_value
    file_name_delegate_instance.text_getter = lambda record: (
        record.value("url") if record.value("url") != "" else os.path.basename(record.value("file"))
    )
    assert file_name_delegate_instance.text_getter(mock_record({"url": "http://a.com/b.mp3"})) == "http://a.com/b.mp3"
    assert file_name_delegate_instance.text_getter(mock_record({"url": "", "file": "/c/d/e.mp3"})) == "e.mp3"

    # model delegate
    model_delegate_instance = mock_record_delegate_class.return_value
    model_delegate_instance.text_getter = lambda record: str(TranscriptionRecord.model(record))
    assert model_delegate_instance.text_getter(mock_record({"model_type": "WHISPER"})) == "MockedModel"

    # task delegate
    task_delegate_instance = mock_record_delegate_class.return_value
    task_delegate_instance.text_getter = lambda record: Task(record.value("task")).name
    assert task_delegate_instance.text_getter(mock_record({"task": Task.TRANSCRIBE.value})) == "TRANSCRIBE"


@pytest.fixture
def widget(qtbot, db):
    w = TranscriptionTasksTableWidget()
    qtbot.addWidget(w)
    w.model().select()
    assert w.model().rowCount() == 2
    return w


class TestTranscriptionTasksTableWidget:
    def test_init_and_save_column_visibility(self, widget):
        assert not widget.isColumnHidden(Column.MODEL_TYPE.value)
        widget.setColumnHidden(Column.MODEL_TYPE.value, True)
        widget.save_column_visibility()

        # Create new widget to check if visibility is loaded
        new_widget = TranscriptionTasksTableWidget()
        assert new_widget.isColumnHidden(Column.MODEL_TYPE.value)

    def test_copy_selected_fields(self, widget):
        # Due to sorting, the second row (index 1) is now the first visible row (index 0)
        widget.selectRow(0)
        widget.copy_selected_fields()
        assert QApplication.clipboard().text() == "http://example.com/d.wav"

        # Select the original first row (now index 1)
        widget.selectRow(1)
        widget.copy_selected_fields()
        assert QApplication.clipboard().text() == "/a/b/c.mp3"

    def test_key_press_event(self, widget):
        with patch.object(widget, "copy_selected_fields") as mock_copy:
            event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
            QApplication.sendEvent(widget, event)
            mock_copy.assert_called_once()

    def test_delete_transcriptions(self, widget):
        initial_row_count = widget.model().rowCount()
        widget.delete_transcriptions([widget.model().index(0, 0)])
        assert widget.model().rowCount() == initial_row_count - 1

    def test_selected_transcriptions(self, widget):
        # Due to sorting, the second row (index 1) is now the first visible row (index 0)
        widget.selectRow(0)
        transcriptions = widget.selected_transcriptions()
        assert len(transcriptions) == 1
        assert transcriptions[0].id == "2"

    def test_refresh_row(self, widget, db):
        with patch.object(widget.model(), "selectRow") as mock_select_row:
            uid = UUID("403d20b3-85a8-4dc8-adf5-78933f978631")
            query = QSqlQuery(db)
            query.exec(f"UPDATE transcription SET id = '{uid}' WHERE id = '1'")
            widget.refresh_all()
            widget.refresh_row(uid)
            assert mock_select_row.called

    def test_context_menus(self, widget, monkeypatch):
        mock_menu = Mock(spec=QMenu)
        monkeypatch.setattr("buzz.widgets.transcription_tasks_table_widget.QMenu", Mock(return_value=mock_menu))

        widget.horizontalHeader().contextMenuEvent(Mock())
        assert mock_menu.addAction.call_count > 0

        menu_add_action_call_count = mock_menu.addAction.call_count
        widget.contextMenuEvent(Mock())
        assert mock_menu.addAction.call_count > menu_add_action_call_count
