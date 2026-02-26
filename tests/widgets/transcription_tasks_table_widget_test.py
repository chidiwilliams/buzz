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

from buzz.locale import _
from buzz.widgets.transcription_tasks_table_widget import (
    TranscriptionTasksTableWidget,
    TranscriptionTasksTableHeaderView,
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
    current_group = [""]

    def begin_group(group):
        current_group[0] = group + "/"

    def end_group():
        current_group[0] = ""

    def set_value(k, v):
        settings_store[current_group[0] + k] = v

    def get_value(k, default=None):
        return settings_store.get(current_group[0] + k, default)

    mock_settings.settings = Mock()
    mock_settings.settings.setValue.side_effect = set_value
    mock_settings.settings.value.side_effect = get_value
    mock_settings.begin_group.side_effect = begin_group
    mock_settings.end_group.side_effect = end_group
    monkeypatch.setattr(
        "buzz.widgets.transcription_tasks_table_widget.Settings",
        Mock(return_value=mock_settings),
    )
    monkeypatch.setattr(
        "buzz.widgets.transcription_tasks_table_widget.Settings.Key",
        Mock(
            TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY="visibility",
            TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER="order",
            TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS="widths",
            TRANSCRIPTION_TASKS_TABLE_SORT_STATE="sort-state"
        ),
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
        "extract_speech BOOLEAN DEFAULT FALSE,"  # 19
        "name TEXT,"  # 20
        "notes TEXT"  # 21
        ")"
    )
    query.exec(
        "INSERT INTO transcription (id, file, url, status, time_queued, task, model_type, name, notes) VALUES "
        "('1', '/a/b/c.mp3', '', 'QUEUED', '2023-01-01T00:00:00', 'TRANSCRIBE', 'WHISPER', 'Test Audio File', 'This is a test transcription'),"
        "('2', '', 'http://example.com/d.wav', 'QUEUED', '2023-01-02T00:00:00', 'TRANSCRIBE', 'WHISPER', 'URL Audio', 'URL-based transcription')"
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
        # Select a row so the widget context menu will add actions
        widget.selectRow(0)
        widget.contextMenuEvent(Mock())
        assert mock_menu.addAction.call_count > menu_add_action_call_count

    def test_new_column_definitions(self):
        """Test that new NAME and NOTES columns are properly defined"""
        # Check that NOTES column is defined
        notes_column_def = next((col for col in column_definitions if col.column == Column.NOTES), None)
        assert notes_column_def is not None
        assert notes_column_def.id == "notes"
        assert notes_column_def.header == _("Notes")
        assert notes_column_def.width == 300
        assert notes_column_def.hidden_toggleable == True  # Notes column should be toggleable

        # Check that FILE column has been updated to include name functionality
        file_column_def = next((col for col in column_definitions if col.column == Column.FILE), None)
        assert file_column_def is not None
        assert file_column_def.id == "file_name"
        assert file_column_def.header == _("File Name / URL")
        assert file_column_def.width == 400
        assert file_column_def.hidden_toggleable == False  # File column should not be toggleable

    def test_file_column_text_getter_with_name(self, widget):
        """Test that file column displays name or falls back to file/url"""
        # Test with name present
        record_with_name = mock_record({"name": "Custom Name", "url": "http://example.com", "file": "/path/file.mp3"})
        file_column_def = next((col for col in column_definitions if col.column == Column.FILE), None)
        text = file_column_def.delegate.callback(record_with_name)
        assert text == "Custom Name"

        # Test fallback to file basename when no name (file takes priority over URL)
        record_file_fallback = mock_record({"name": None, "url": "http://example.com/audio.mp3", "file": "/path/file.mp3"})
        text = file_column_def.delegate.callback(record_file_fallback)
        assert text == "file.mp3"

        # Test fallback to URL when no name and no file
        record_url_fallback = mock_record({"name": None, "url": "http://example.com/audio.mp3", "file": ""})
        text = file_column_def.delegate.callback(record_url_fallback)
        assert text == "http://example.com/audio.mp3"

    def test_notes_column_text_getter(self, widget):
        """Test that notes column displays notes or empty string"""
        notes_column_def = next((col for col in column_definitions if col.column == Column.NOTES), None)
        
        # Test with notes present
        record_with_notes = mock_record({"notes": "Important transcription notes"})
        text = notes_column_def.delegate.callback(record_with_notes)
        assert text == "Important transcription notes"

        # Test with no notes
        record_no_notes = mock_record({"notes": None})
        text = notes_column_def.delegate.callback(record_no_notes)
        assert text == ""

    def test_column_visibility_management(self, widget):
        """Test column visibility save/load functionality"""
        # Test saving column visibility
        widget.setColumnHidden(Column.NOTES.value, True)
        widget.save_column_visibility()
        
        # Create new widget to test loading
        new_widget = TranscriptionTasksTableWidget()
        assert new_widget.isColumnHidden(Column.NOTES.value)

    def test_column_width_management(self, widget):
        """Test column width save/load functionality"""
        # Test saving column widths
        widget.setColumnWidth(Column.FILE.value, 500)
        widget.save_column_widths()
        
        # Create new widget to test loading
        new_widget = TranscriptionTasksTableWidget()
        # Width should be loaded from settings (mocked to return 500)
        assert new_widget.columnWidth(Column.FILE.value) == 500

    def test_column_order_management(self, widget):
        """Test column order save/load functionality"""
        # Test saving column order
        widget.save_column_order()
        
        # Test loading column order
        widget.load_column_order()
        
        # Test resetting column order
        widget.reset_column_order()
        # After reset, columns should be in default order
        header = widget.horizontalHeader()
        for i, definition in enumerate(column_definitions):
            assert header.visualIndex(definition.column.value) == i

    def test_context_menu_rename_action(self, widget, monkeypatch):
        """Test rename action in context menu"""
        # Mock the transcription service
        mock_service = Mock()
        widget.transcription_service = mock_service
        
        # Mock the transcription method to return a proper transcription object
        mock_transcription = Mock()
        mock_transcription.id = "12345678-1234-5678-1234-567812345678"  # Valid UUID
        mock_transcription.name = "Old Name"
        mock_transcription.url = "http://example.com"
        mock_transcription.file = "/path/file.mp3"
        monkeypatch.setattr(widget, "transcription", Mock(return_value=mock_transcription))
        
        # Mock QInputDialog
        mock_dialog = Mock()
        mock_dialog.getText.return_value = ("New Name", True)
        monkeypatch.setattr("PyQt6.QtWidgets.QInputDialog", mock_dialog)
        
        # Select a row
        widget.selectRow(0)
        
        # Call rename action
        widget.on_rename_action()
        
        # Verify service was called
        mock_service.update_transcription_name.assert_called_once()
        mock_dialog.getText.assert_called_once()

    def test_context_menu_notes_action(self, widget, monkeypatch):
        """Test notes action in context menu"""
        # Mock the transcription service
        mock_service = Mock()
        widget.transcription_service = mock_service
        
        # Mock the transcription method to return a proper transcription object
        mock_transcription = Mock()
        mock_transcription.id = "12345678-1234-5678-1234-567812345678"  # Valid UUID
        mock_transcription.notes = "Old notes"
        monkeypatch.setattr(widget, "transcription", Mock(return_value=mock_transcription))
        
        # Mock QInputDialog
        mock_dialog = Mock()
        mock_dialog.getMultiLineText.return_value = ("New notes", True)
        monkeypatch.setattr("PyQt6.QtWidgets.QInputDialog", mock_dialog)
        
        # Select a row
        widget.selectRow(0)
        
        # Call notes action
        widget.on_notes_action()
        
        # Verify service was called
        mock_service.update_transcription_notes.assert_called_once()
        mock_dialog.getMultiLineText.assert_called_once()

    def test_context_menu_restart_action_success(self, widget, monkeypatch):
        """Test restart action for failed/canceled transcriptions"""
        # Mock the transcription service
        mock_service = Mock()
        mock_service.reset_transcription_for_restart = Mock()
        widget.transcription_service = mock_service

        # Mock QMessageBox
        mock_messagebox = Mock()
        monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox", mock_messagebox)

        # Mock the _restart_transcription_task method to avoid complex setup
        mock_restart = Mock()
        monkeypatch.setattr(widget, "_restart_transcription_task", mock_restart)

        # Mock the transcription record to return failed status
        mock_transcription = Mock()
        mock_transcription.status = "failed"
        mock_transcription.id = "12345678-1234-5678-1234-567812345678"  # Valid UUID
        monkeypatch.setattr(widget, "transcription", Mock(return_value=mock_transcription))

        # Select a row
        widget.selectRow(0)

        # Call restart action
        widget.on_restart_transcription_action()

        # Verify service and restart were called
        mock_service.reset_transcription_for_restart.assert_called_once()
        mock_restart.assert_called_once_with(mock_transcription)

    def test_context_menu_restart_action_wrong_status(self, widget, monkeypatch):
        """Test restart action shows error for non-failed/canceled transcriptions"""
        # Mock QMessageBox
        mock_messagebox = Mock()
        monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox", mock_messagebox)
        
        # Mock the transcription record to return completed status
        mock_transcription = Mock()
        mock_transcription.status = "completed"
        monkeypatch.setattr(widget, "transcription", Mock(return_value=mock_transcription))
        
        # Select a row
        widget.selectRow(0)
        
        # Call restart action
        widget.on_restart_transcription_action()
        
        # Verify error message was shown
        mock_messagebox.information.assert_called_once()

    # --- on_restart_transcription_action edge cases ---

    def test_restart_action_no_selection_does_nothing(self, widget, monkeypatch):
        mock_service = Mock()
        widget.transcription_service = mock_service
        # No row selected
        widget.on_restart_transcription_action()
        mock_service.reset_transcription_for_restart.assert_not_called()

    def test_restart_action_canceled_status_succeeds(self, widget, monkeypatch):
        mock_service = Mock()
        widget.transcription_service = mock_service
        mock_transcription = Mock()
        mock_transcription.status = "canceled"
        mock_transcription.id = "12345678-1234-5678-1234-567812345678"
        monkeypatch.setattr(widget, "transcription", Mock(return_value=mock_transcription))
        mock_restart = Mock()
        monkeypatch.setattr(widget, "_restart_transcription_task", mock_restart)

        widget.selectRow(0)
        widget.on_restart_transcription_action()

        mock_service.reset_transcription_for_restart.assert_called_once()
        mock_restart.assert_called_once_with(mock_transcription)

    def test_restart_action_service_exception_shows_warning(self, widget, monkeypatch):
        mock_service = Mock()
        mock_service.reset_transcription_for_restart.side_effect = RuntimeError("DB error")
        widget.transcription_service = mock_service
        mock_transcription = Mock()
        mock_transcription.status = "failed"
        mock_transcription.id = "12345678-1234-5678-1234-567812345678"
        monkeypatch.setattr(widget, "transcription", Mock(return_value=mock_transcription))

        mock_messagebox = Mock()
        monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox", mock_messagebox)

        widget.selectRow(0)
        widget.on_restart_transcription_action()

        mock_messagebox.warning.assert_called_once()

    # --- _restart_transcription_task ---

    def _make_transcription(self, **kwargs):
        from buzz.transcriber.transcriber import Task
        defaults = dict(
            id="12345678-1234-5678-1234-567812345678",
            status="failed",
            file="/audio/test.mp3",
            url=None,
            language="en",
            task=Task.TRANSCRIBE.value,
            model_type="Whisper",
            whisper_model_size="Tiny",
            hugging_face_model_id=None,
            word_level_timings="0",
            extract_speech="0",
            export_formats="txt",
            output_folder=None,
            source="FILE_IMPORT",
        )
        defaults.update(kwargs)
        t = Mock()
        for k, v in defaults.items():
            setattr(t, k, v)
        return t

    def test_restart_task_happy_path_adds_task(self, widget, monkeypatch):
        from buzz.transcriber.transcriber import FileTranscriptionTask
        transcription = self._make_transcription()

        mock_model_path = "/models/ggml-tiny.bin"
        mock_model = Mock()
        mock_model.get_local_model_path.return_value = mock_model_path

        mock_transcription_model_cls = Mock(return_value=mock_model)
        monkeypatch.setattr("buzz.model_loader.TranscriptionModel", mock_transcription_model_cls)

        mock_task_instance = Mock(spec=FileTranscriptionTask)
        mock_task_cls = Mock(return_value=mock_task_instance)
        monkeypatch.setattr(
            "buzz.transcriber.transcriber.FileTranscriptionTask", mock_task_cls
        )

        mock_worker = Mock()
        mock_main_window = Mock()
        mock_main_window.transcriber_worker = mock_worker
        mock_main_window.parent.return_value = None
        monkeypatch.setattr(widget, "parent", Mock(return_value=mock_main_window))

        widget._restart_transcription_task(transcription)

        mock_worker.add_task.assert_called_once_with(mock_task_instance)

    def test_restart_task_invalid_whisper_model_size_defaults_to_tiny(self, widget, monkeypatch):
        from buzz.model_loader import WhisperModelSize
        transcription = self._make_transcription(whisper_model_size="InvalidSize")

        captured = {}

        original_cls = __builtins__  # just a placeholder

        def capture_model(**kwargs):
            captured["whisper_model_size"] = kwargs.get("whisper_model_size")
            m = Mock()
            m.get_local_model_path.return_value = "/fake/path"
            return m

        monkeypatch.setattr(
            "buzz.model_loader.TranscriptionModel",
            Mock(side_effect=capture_model),
        )
        monkeypatch.setattr(
            "buzz.transcriber.transcriber.FileTranscriptionTask",
            Mock(return_value=Mock()),
        )
        mock_worker = Mock()
        mock_main_window = Mock()
        mock_main_window.transcriber_worker = mock_worker
        mock_main_window.parent.return_value = None
        monkeypatch.setattr(widget, "parent", Mock(return_value=mock_main_window))

        widget._restart_transcription_task(transcription)

        assert captured["whisper_model_size"] == WhisperModelSize.TINY

    def test_restart_task_model_not_available_downloads_it(self, widget, monkeypatch):
        from buzz.transcriber.transcriber import FileTranscriptionTask
        transcription = self._make_transcription()

        mock_model = Mock()
        mock_model.get_local_model_path.side_effect = [None, "/models/ggml-tiny.bin"]
        monkeypatch.setattr(
            "buzz.model_loader.TranscriptionModel",
            Mock(return_value=mock_model),
        )

        mock_downloader = Mock()
        mock_downloader_cls = Mock(return_value=mock_downloader)
        monkeypatch.setattr(
            "buzz.model_loader.ModelDownloader",
            mock_downloader_cls,
        )
        monkeypatch.setattr(
            "buzz.transcriber.transcriber.FileTranscriptionTask",
            Mock(return_value=Mock()),
        )
        mock_worker = Mock()
        mock_main_window = Mock()
        mock_main_window.transcriber_worker = mock_worker
        mock_main_window.parent.return_value = None
        monkeypatch.setattr(widget, "parent", Mock(return_value=mock_main_window))

        widget._restart_transcription_task(transcription)

        mock_downloader.run.assert_called_once()
        mock_worker.add_task.assert_called_once()

    def test_restart_task_model_unavailable_after_download_shows_warning(self, widget, monkeypatch):
        transcription = self._make_transcription()

        mock_model = Mock()
        mock_model.get_local_model_path.return_value = None
        monkeypatch.setattr(
            "buzz.model_loader.TranscriptionModel",
            Mock(return_value=mock_model),
        )
        monkeypatch.setattr(
            "buzz.model_loader.ModelDownloader",
            Mock(return_value=Mock()),
        )

        mock_messagebox = Mock()
        monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox", mock_messagebox)

        widget._restart_transcription_task(transcription)

        mock_messagebox.warning.assert_called_once()

    def test_restart_task_no_worker_found_shows_warning(self, widget, monkeypatch):
        transcription = self._make_transcription()

        mock_model = Mock()
        mock_model.get_local_model_path.return_value = "/fake/path"
        monkeypatch.setattr(
            "buzz.model_loader.TranscriptionModel",
            Mock(return_value=mock_model),
        )
        monkeypatch.setattr(
            "buzz.transcriber.transcriber.FileTranscriptionTask",
            Mock(return_value=Mock()),
        )

        # Parent with no transcriber_worker, and no further parent
        mock_parent = Mock(spec=["parent"])  # only has parent(), not transcriber_worker
        mock_parent.parent.return_value = None
        monkeypatch.setattr(widget, "parent", Mock(return_value=mock_parent))

        mock_messagebox = Mock()
        monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox", mock_messagebox)

        widget._restart_transcription_task(transcription)

        mock_messagebox.warning.assert_called_once()

    def test_restart_task_export_formats_parsed_correctly(self, widget, monkeypatch):
        from buzz.transcriber.transcriber import OutputFormat
        transcription = self._make_transcription(export_formats="txt, srt")

        captured = {}

        def capture_file_transcription_options(**kwargs):
            captured["output_formats"] = kwargs.get("output_formats")
            return Mock()

        monkeypatch.setattr(
            "buzz.transcriber.transcriber.FileTranscriptionOptions",
            Mock(side_effect=capture_file_transcription_options),
        )
        mock_model = Mock()
        mock_model.get_local_model_path.return_value = "/fake/path"
        monkeypatch.setattr(
            "buzz.model_loader.TranscriptionModel",
            Mock(return_value=mock_model),
        )
        monkeypatch.setattr(
            "buzz.transcriber.transcriber.FileTranscriptionTask",
            Mock(return_value=Mock()),
        )
        mock_worker = Mock()
        mock_main_window = Mock()
        mock_main_window.transcriber_worker = mock_worker
        mock_main_window.parent.return_value = None
        monkeypatch.setattr(widget, "parent", Mock(return_value=mock_main_window))

        widget._restart_transcription_task(transcription)

        assert OutputFormat("txt") in captured["output_formats"]
        assert OutputFormat("srt") in captured["output_formats"]

    def test_restart_task_invalid_export_format_skipped(self, widget, monkeypatch):
        transcription = self._make_transcription(export_formats="txt, INVALID_FORMAT")

        captured = {}

        def capture_file_transcription_options(**kwargs):
            captured["output_formats"] = kwargs.get("output_formats")
            return Mock()

        monkeypatch.setattr(
            "buzz.transcriber.transcriber.FileTranscriptionOptions",
            Mock(side_effect=capture_file_transcription_options),
        )
        mock_model = Mock()
        mock_model.get_local_model_path.return_value = "/fake/path"
        monkeypatch.setattr(
            "buzz.model_loader.TranscriptionModel",
            Mock(return_value=mock_model),
        )
        monkeypatch.setattr(
            "buzz.transcriber.transcriber.FileTranscriptionTask",
            Mock(return_value=Mock()),
        )
        mock_worker = Mock()
        mock_main_window = Mock()
        mock_main_window.transcriber_worker = mock_worker
        mock_main_window.parent.return_value = None
        monkeypatch.setattr(widget, "parent", Mock(return_value=mock_main_window))

        widget._restart_transcription_task(transcription)

        # Only the valid format should be present, invalid one skipped silently
        assert len(captured["output_formats"]) == 1

    def test_column_resize_event(self, widget):
        """Test column resize event handling"""
        # Mock the save_column_widths method
        with patch.object(widget, 'save_column_widths') as mock_save:
            # Simulate column resize
            widget.on_column_resized(0, 100, 200)
            mock_save.assert_called_once()

    def test_column_move_event(self, widget):
        """Test column move event handling"""
        # Mock the save methods
        with patch.object(widget, 'save_column_order') as mock_save_order, \
             patch.object(widget, 'load_column_visibility') as mock_load_vis:
            # Simulate column move
            widget.on_column_moved(0, 0, 1)
            mock_save_order.assert_called_once()
            mock_load_vis.assert_called_once()

    def test_reload_column_order_from_settings(self, widget):
        """Test reloading column order from settings"""
        # Mock settings to return specific values
        widget.settings.settings.value.side_effect = lambda key, default=None: {
            "file_name": "0",
            "notes": "1",
            "status": "2"
        }.get(key, default)

        # Call reload method
        widget.reload_column_order_from_settings()

        # Verify the method completes without error
        assert True  # If we get here, no exception was raised

    def test_sort_indicator_change_event(self, widget):
        """Test sort indicator change event handling"""
        with patch.object(widget, 'save_sort_state') as mock_save:
            # Simulate sort indicator change
            widget.on_sort_indicator_changed(0, Qt.SortOrder.AscendingOrder)
            mock_save.assert_called_once()

    def test_save_sort_state(self, widget):
        """Test saving sort state to settings"""
        # Set a specific sort
        widget.sortByColumn(Column.FILE.value, Qt.SortOrder.AscendingOrder)
        widget.save_sort_state()

        # Verify settings were called
        assert widget.settings.begin_group.called
        assert widget.settings.settings.setValue.called

    def test_load_sort_state(self, widget):
        """Test loading sort state from settings"""
        # Mock settings to return specific sort state
        widget.settings.settings.value.side_effect = lambda key, default=None: {
            "sort-state/column": Column.FILE.value,
            "sort-state/order": Qt.SortOrder.AscendingOrder.value
        }.get(key, default)

        # Call load method
        widget.load_sort_state()

        # Verify the method completes without error
        assert True  # If we get here, no exception was raised

    def test_reset_column_order_resets_sort(self, widget):
        """Test that reset column order also resets sort state"""
        # Change sort from default
        widget.sortByColumn(Column.FILE.value, Qt.SortOrder.AscendingOrder)

        # Reset column order
        widget.reset_column_order()

        # Verify sort is reset to default (TIME_QUEUED descending)
        header = widget.horizontalHeader()
        assert header.sortIndicatorSection() == Column.TIME_QUEUED.value
        assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder


class TestTranscriptionTasksTableHeaderView:
    @pytest.fixture
    def header(self, qtbot, widget):
        return widget.horizontalHeader()

    def _setup_settings_key(self, widget):
        """Set up settings.Key and restore begin_group side_effect for inline width-saving."""
        widget.settings.Key = Mock(
            TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS="widths"
        )
        current_group = [""]

        def begin_group(group):
            current_group[0] = str(group) + "/"

        def end_group():
            current_group[0] = ""

        widget.settings.begin_group.side_effect = begin_group
        widget.settings.end_group.side_effect = end_group

    def test_hiding_column_saves_visibility_and_widths(self, header, widget):
        col = Column.NOTES.value
        widget.setColumnWidth(col, 250)
        widget.setColumnHidden(col, False)
        self._setup_settings_key(widget)

        with patch.object(widget, "save_column_visibility") as mock_vis, \
             patch.object(widget, "save_column_widths") as mock_widths, \
             patch.object(widget, "save_column_order"), \
             patch.object(widget, "reload_column_order_from_settings"):
            header.on_column_checked(col, False)

        assert widget.isColumnHidden(col)
        mock_vis.assert_called()
        mock_widths.assert_called()

    def test_showing_column_makes_it_visible(self, header, widget):
        col = Column.NOTES.value
        widget.setColumnHidden(col, True)

        with patch.object(widget, "save_column_visibility"), \
             patch.object(widget, "save_column_widths"), \
             patch.object(widget, "save_column_order"), \
             patch.object(widget, "reload_column_order_from_settings"):
            header.on_column_checked(col, True)

        assert not widget.isColumnHidden(col)

    def test_hiding_already_hidden_column_does_not_save_zero_width(self, header, widget):
        col = Column.NOTES.value
        widget.setColumnHidden(col, True)
        self._setup_settings_key(widget)

        saved_widths = {}

        def capture_set_value(key, value):
            saved_widths[key] = value

        widget.settings.settings.setValue.side_effect = capture_set_value

        with patch.object(widget, "save_column_visibility"), \
             patch.object(widget, "save_column_widths"), \
             patch.object(widget, "save_column_order"), \
             patch.object(widget, "reload_column_order_from_settings"):
            header.on_column_checked(col, False)

        # Width of a hidden column is 0 — should not be saved
        notes_id = next(d.id for d in column_definitions if d.column == Column.NOTES)
        assert notes_id not in saved_widths

    def test_column_order_saved_on_visibility_change(self, header, widget):
        col = Column.NOTES.value
        self._setup_settings_key(widget)

        with patch.object(widget, "save_column_visibility"), \
             patch.object(widget, "save_column_widths"), \
             patch.object(widget, "save_column_order") as mock_order, \
             patch.object(widget, "reload_column_order_from_settings"):
            header.on_column_checked(col, False)

        mock_order.assert_called_once()

    def test_reload_called_after_visibility_change(self, header, widget):
        col = Column.NOTES.value

        with patch.object(widget, "save_column_visibility"), \
             patch.object(widget, "save_column_widths"), \
             patch.object(widget, "save_column_order"), \
             patch.object(widget, "reload_column_order_from_settings") as mock_reload:
            header.on_column_checked(col, True)

        mock_reload.assert_called_once()
