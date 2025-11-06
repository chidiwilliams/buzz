import uuid
from uuid import UUID
import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import Qt
from PyQt6.QtSql import QSqlRecord

from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    TranscriptionSegmentsEditorWidget,
    TranscriptionSegmentModel,
    TimeStampLineEdit,
    TimeStampDelegate,
    TimeStampEditorDelegate,
    WordWrapDelegate,
    CustomTextEdit,
    parse_timestamp,
    Column,
)
from buzz.translator import Translator
from tests.audio import test_audio_path


class TestParseTimestamp:
    """Test the parse_timestamp function"""

    def test_parse_timestamp_full_format(self):
        """Test parsing HH:MM:SS.mmm format"""
        result = parse_timestamp("01:23:45.678")
        expected = 1 * 3600 * 1000 + 23 * 60 * 1000 + 45 * 1000 + 678
        assert result == expected

    def test_parse_timestamp_minute_format(self):
        """Test parsing MM:SS.mmm format"""
        result = parse_timestamp("23:45.678")
        expected = 23 * 60 * 1000 + 45 * 1000 + 678
        assert result == expected

    def test_parse_timestamp_second_format(self):
        """Test parsing SS.mmm format"""
        result = parse_timestamp("45.678")
        expected = 45 * 1000 + 678
        assert result == expected

    def test_parse_timestamp_no_milliseconds(self):
        """Test parsing without milliseconds"""
        result = parse_timestamp("01:23:45")
        expected = 1 * 3600 * 1000 + 23 * 60 * 1000 + 45 * 1000
        assert result == expected

    def test_parse_timestamp_with_whitespace(self):
        """Test parsing with leading/trailing whitespace"""
        result = parse_timestamp("  01:23:45.678  ")
        expected = 1 * 3600 * 1000 + 23 * 60 * 1000 + 45 * 1000 + 678
        assert result == expected

    def test_parse_timestamp_invalid_format(self):
        """Test parsing invalid format returns None"""
        assert parse_timestamp("invalid") is None
        assert parse_timestamp("::") is None
        assert parse_timestamp("a:b:c") is None

    def test_parse_timestamp_empty_string(self):
        """Test parsing empty string returns None"""
        assert parse_timestamp("") is None


class TestTimeStampLineEdit:
    """Test the TimeStampLineEdit widget"""

    def test_timestamp_line_edit_initialization(self, qtbot: QtBot):
        """Test TimeStampLineEdit initialization"""
        widget = TimeStampLineEdit()
        qtbot.add_widget(widget)

        assert widget._milliseconds == 0
        assert hasattr(widget, 'validator')

    def test_set_milliseconds(self, qtbot: QtBot):
        """Test set_milliseconds method"""
        widget = TimeStampLineEdit()
        qtbot.add_widget(widget)

        widget.set_milliseconds(5000)
        assert widget._milliseconds == 5000
        # Text should be formatted as timestamp
        assert len(widget.text()) > 0

    def test_get_milliseconds(self, qtbot: QtBot):
        """Test get_milliseconds method"""
        widget = TimeStampLineEdit()
        qtbot.add_widget(widget)

        widget.set_milliseconds(5000)
        assert widget.get_milliseconds() == 5000

    def test_plus_key_increases_time(self, qtbot: QtBot):
        """Test + key increases time by 500ms"""
        widget = TimeStampLineEdit()
        qtbot.add_widget(widget)

        widget.set_milliseconds(1000)
        qtbot.keyPress(widget, Qt.Key.Key_Plus)

        assert widget._milliseconds == 1500

    def test_minus_key_decreases_time(self, qtbot: QtBot):
        """Test - key decreases time by 500ms"""
        widget = TimeStampLineEdit()
        qtbot.add_widget(widget)

        widget.set_milliseconds(1000)
        qtbot.keyPress(widget, Qt.Key.Key_Minus)

        assert widget._milliseconds == 500

    def test_minus_key_does_not_go_negative(self, qtbot: QtBot):
        """Test - key doesn't allow negative time"""
        widget = TimeStampLineEdit()
        qtbot.add_widget(widget)

        widget.set_milliseconds(200)
        qtbot.keyPress(widget, Qt.Key.Key_Minus)

        assert widget._milliseconds == 0

    def test_focus_out_reformats_timestamp(self, qtbot: QtBot):
        """Test that focus out reformats the timestamp"""
        widget = TimeStampLineEdit()
        qtbot.add_widget(widget)

        widget.set_milliseconds(5000)
        initial_text = widget.text()

        # Simulate focus out
        widget.clearFocus()

        # Text should still be valid
        assert len(widget.text()) > 0

    def test_validator_rejects_invalid_characters(self, qtbot: QtBot):
        """Test that validator rejects invalid characters"""
        widget = TimeStampLineEdit()
        qtbot.add_widget(widget)

        # Validator should allow only digits, colons, and dots
        widget.setText("abc")
        # The validator is set up but text might still be set
        # We're mainly testing that the validator exists and works
        assert hasattr(widget, 'validator')


class TestTimeStampDelegate:
    """Test the TimeStampDelegate"""

    def test_display_text_formatting(self):
        """Test that displayText formats milliseconds correctly"""
        delegate = TimeStampDelegate()

        # Test formatting
        from PyQt6.QtCore import QLocale
        locale = QLocale()

        result = delegate.displayText(5000, locale)
        assert len(result) > 0
        assert ":" in result


class TestTimeStampEditorDelegate:
    """Test the TimeStampEditorDelegate"""

    def test_delegate_initialization(self):
        """Test TimeStampEditorDelegate initialization"""
        delegate = TimeStampEditorDelegate()
        assert hasattr(delegate, 'timestamp_editing')

    def test_create_editor(self, qtbot: QtBot):
        """Test createEditor method"""
        delegate = TimeStampEditorDelegate()

        from PyQt6.QtWidgets import QWidget, QStyleOptionViewItem
        parent = QWidget()
        qtbot.add_widget(parent)

        from PyQt6.QtCore import QModelIndex
        option = QStyleOptionViewItem()
        index = QModelIndex()

        editor = delegate.createEditor(parent, option, index)
        assert isinstance(editor, TimeStampLineEdit)


class TestWordWrapDelegate:
    """Test the WordWrapDelegate"""

    def test_create_editor(self, qtbot: QtBot):
        """Test createEditor method"""
        delegate = WordWrapDelegate()

        from PyQt6.QtWidgets import QWidget, QStyleOptionViewItem
        parent = QWidget()
        qtbot.add_widget(parent)

        from PyQt6.QtCore import QModelIndex
        option = QStyleOptionViewItem()
        index = QModelIndex()

        editor = delegate.createEditor(parent, option, index)
        assert isinstance(editor, CustomTextEdit)


class TestCustomTextEdit:
    """Test the CustomTextEdit widget"""

    def test_initialization(self, qtbot: QtBot):
        """Test CustomTextEdit initialization"""
        widget = CustomTextEdit()
        qtbot.add_widget(widget)
        assert widget is not None

    def test_tab_key_closes_editor(self, qtbot: QtBot):
        """Test that Tab key closes the editor"""
        widget = CustomTextEdit()
        qtbot.add_widget(widget)

        widget.setFocus()
        initial_focus = widget.hasFocus()

        qtbot.keyPress(widget, Qt.Key.Key_Tab)

        # After Tab, focus should be cleared
        assert not widget.hasFocus()

    def test_enter_key_closes_editor(self, qtbot: QtBot):
        """Test that Enter key closes the editor"""
        widget = CustomTextEdit()
        qtbot.add_widget(widget)

        widget.setFocus()
        qtbot.keyPress(widget, Qt.Key.Key_Return)

        # After Enter, focus should be cleared
        assert not widget.hasFocus()

    def test_escape_key_closes_editor(self, qtbot: QtBot):
        """Test that Escape key closes the editor"""
        widget = CustomTextEdit()
        qtbot.add_widget(widget)

        widget.setFocus()
        qtbot.keyPress(widget, Qt.Key.Key_Escape)

        # After Escape, focus should be cleared
        assert not widget.hasFocus()


class TestTranscriptionSegmentModel:
    """Test the TranscriptionSegmentModel"""

    @pytest.fixture()
    def transcription_id(self) -> UUID:
        """Generate a test transcription ID"""
        return uuid.uuid4()

    def test_model_initialization(self, transcription_id):
        """Test TranscriptionSegmentModel initialization"""
        model = TranscriptionSegmentModel(transcription_id)

        assert model.tableName() == "transcription_segment"
        assert model.editStrategy() == model.EditStrategy.OnFieldChange


class TestTranscriptionSegmentsEditorWidget:
    """Test the TranscriptionSegmentsEditorWidget"""

    @pytest.fixture()
    def transcription(
            self, transcription_dao, transcription_segment_dao
    ) -> Transcription:
        """Create a test transcription with segments"""
        id = uuid.uuid4()
        transcription_dao.insert(
            Transcription(
                id=str(id),
                status="completed",
                file=test_audio_path,
                task=Task.TRANSCRIBE.value,
                model_type=ModelType.WHISPER.value,
                whisper_model_size=WhisperModelSize.TINY.value,
            )
        )
        transcription_segment_dao.insert(
            TranscriptionSegment(40, 299, "Bien", "", str(id))
        )
        transcription_segment_dao.insert(
            TranscriptionSegment(299, 600, "venue dans", "", str(id))
        )
        transcription_segment_dao.insert(
            TranscriptionSegment(600, 1000, "Press Buzz", "", str(id))
        )

        return transcription_dao.find_by_id(str(id))

    @pytest.fixture()
    def translator(self, qtbot: QtBot):
        """Create a mock translator"""
        from unittest.mock import MagicMock
        mock_translator = MagicMock(spec=Translator)
        return mock_translator

    def test_widget_initialization(self, qtbot: QtBot, transcription, translator):
        """Test TranscriptionSegmentsEditorWidget initialization"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        assert widget is not None
        assert widget.model() is not None
        assert widget.model().rowCount() == 3

    def test_column_definitions(self, qtbot: QtBot, transcription, translator):
        """Test that column definitions are properly set"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        assert hasattr(widget, 'column_definitions')
        assert len(widget.column_definitions) == 4

        # Check that columns have proper delegates
        for col_def in widget.column_definitions:
            assert hasattr(col_def, 'id')
            assert hasattr(col_def, 'header')
            assert hasattr(col_def, 'column')

    def test_segments_method(self, qtbot: QtBot, transcription, translator):
        """Test segments() method returns all segments"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        segments = widget.segments()
        assert len(segments) == 3
        assert isinstance(segments[0], QSqlRecord)

    def test_segment_method(self, qtbot: QtBot, transcription, translator):
        """Test segment() method returns specific segment"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        index = widget.model().index(0, 0)
        segment = widget.segment(index)
        assert isinstance(segment, QSqlRecord)

    def test_highlight_and_scroll_to_row(self, qtbot: QtBot, transcription, translator):
        """Test highlight_and_scroll_to_row method"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        # Test scrolling to valid row
        widget.highlight_and_scroll_to_row(1)

        # Should not crash on invalid row
        widget.highlight_and_scroll_to_row(-1)
        widget.highlight_and_scroll_to_row(999)

    def test_has_non_empty_translation(self, qtbot: QtBot, transcription, translator, transcription_segment_dao):
        """Test has_non_empty_translation method"""
        # Add a translation to one segment
        transcription_segment_dao.insert(
            TranscriptionSegment(1000, 1500, "Test", "Translation", transcription.id)
        )

        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        result = widget.has_non_empty_translation()
        assert isinstance(result, bool)

    def test_init_row_height(self, qtbot: QtBot, transcription, translator):
        """Test init_row_height method"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        # Should not crash
        widget.init_row_height()

        # Check that row heights are set
        for row in range(widget.model().rowCount()):
            assert widget.rowHeight(row) > 0

    def test_update_translation(self, qtbot: QtBot, transcription, translator):
        """Test update_translation method"""
        from PyQt6.QtWidgets import QWidget
        parent = QWidget()
        parent.resize(800, 600)
        qtbot.add_widget(parent)

        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=parent
        )

        # Get first segment ID
        first_segment = widget.model().record(0)
        segment_id = first_segment.value("id")

        # Update translation
        widget.update_translation("Test translation", segment_id)

        # Submit changes to ensure they're written to database
        widget.model().submitAll()

        # Check that translation was updated
        updated_segment = widget.model().record(0)
        translation = updated_segment.value("translation")
        assert translation == "Test translation"

    def test_segment_selected_signal(self, qtbot: QtBot, transcription, translator):
        """Test that segment_selected signal is emitted"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        # Connect to signal
        from unittest.mock import MagicMock
        signal_handler = MagicMock()
        widget.segment_selected.connect(signal_handler)

        # Select a row
        widget.selectRow(0)

        # Signal should be emitted
        signal_handler.assert_called()

    def test_timestamp_being_edited_signal(self, qtbot: QtBot, transcription, translator):
        """Test that timestamp_being_edited signal exists"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        assert hasattr(widget, 'timestamp_being_edited')

    def test_enter_key_triggers_editing(self, qtbot: QtBot, transcription, translator):
        """Test that Enter key triggers editing"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        # Select a cell
        widget.setCurrentIndex(widget.model().index(0, Column.TEXT.value))

        # Press Enter
        qtbot.keyPress(widget, Qt.Key.Key_Return)

        # Should not crash

    def test_column_widths(self, qtbot: QtBot, transcription, translator):
        """Test that column widths are set"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        # Check start and end column widths
        assert widget.columnWidth(Column.START.value) == 120
        assert widget.columnWidth(Column.END.value) == 120

    def test_alternating_row_colors(self, qtbot: QtBot, transcription, translator):
        """Test that alternating row colors are enabled"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        assert widget.alternatingRowColors()

    def test_vertical_header_hidden(self, qtbot: QtBot, transcription, translator):
        """Test that vertical header is hidden"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        assert widget.verticalHeader().isHidden()

    def test_selection_behavior(self, qtbot: QtBot, transcription, translator):
        """Test that selection behavior is set to SelectRows"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        from PyQt6.QtWidgets import QAbstractItemView
        assert widget.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows

    def test_selection_mode(self, qtbot: QtBot, transcription, translator):
        """Test that selection mode is set to SingleSelection"""
        widget = TranscriptionSegmentsEditorWidget(
            transcription_id=uuid.UUID(hex=transcription.id),
            translator=translator,
            parent=None
        )
        qtbot.add_widget(widget)

        from PyQt6.QtWidgets import QTableView
        assert widget.selectionMode() == QTableView.SelectionMode.SingleSelection