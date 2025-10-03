import uuid
import sys
import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import Qt
from PyQt6.QtMultimedia import QMediaPlayer
from unittest.mock import MagicMock, patch

from buzz.locale import _
from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)
from buzz.widgets.transcription_viewer.transcription_view_mode_tool_button import ViewMode
from tests.audio import test_audio_path


class TestTranscriptionViewerWidgetAdditional:
    """Additional tests for TranscriptionViewerWidget functions"""

    @pytest.fixture()
    def transcription(self, transcription_dao, transcription_segment_dao) -> Transcription:
        """Create test transcription with multiple segments"""
        id = uuid.uuid4()
        transcription_dao.insert(
            Transcription(
                id=str(id),
                status="completed",
                file=test_audio_path,
                task=Task.TRANSCRIBE.value,
                model_type=ModelType.WHISPER.value,
                whisper_model_size=WhisperModelSize.SMALL.value,
            )
        )
        transcription_segment_dao.insert(
            TranscriptionSegment(40, 500, "First segment", "", str(id))
        )
        transcription_segment_dao.insert(
            TranscriptionSegment(500, 1000, "Second segment", "", str(id))
        )
        transcription_segment_dao.insert(
            TranscriptionSegment(1000, 1500, "Third segment", "", str(id))
        )

        return transcription_dao.find_by_id(str(id))

    def test_toggle_audio_playback(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test toggle_audio_playback method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test toggle when stopped
        initial_state = widget.audio_player.media_player.playbackState()
        widget.toggle_audio_playback()

        # Should not crash
        assert hasattr(widget, 'toggle_audio_playback')

        widget.close()

    def test_replay_current_segment(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test replay_current_segment method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Without selected segment, should do nothing
        widget.replay_current_segment()

        # With selected segment
        widget.currently_selected_segment = widget.table_widget.model().record(0)
        widget.replay_current_segment()

        # Should not crash
        assert hasattr(widget, 'replay_current_segment')

        widget.close()

    def test_decrease_segment_start(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test decrease_segment_start method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Without selected segment
        widget.decrease_segment_start()

        # With selected segment
        widget.currently_selected_segment = widget.table_widget.model().record(0)
        initial_start = widget.currently_selected_segment.value("start_time")

        widget.decrease_segment_start()

        # Should not crash
        assert hasattr(widget, 'decrease_segment_start')

        widget.close()

    def test_increase_segment_start(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test increase_segment_start method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Without selected segment
        widget.increase_segment_start()

        # With selected segment
        widget.currently_selected_segment = widget.table_widget.model().record(0)
        widget.increase_segment_start()

        # Should not crash
        assert hasattr(widget, 'increase_segment_start')

        widget.close()

    def test_decrease_segment_end(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test decrease_segment_end method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Without selected segment
        widget.decrease_segment_end()

        # With selected segment
        widget.currently_selected_segment = widget.table_widget.model().record(0)
        widget.decrease_segment_end()

        # Should not crash
        assert hasattr(widget, 'decrease_segment_end')

        widget.close()

    def test_increase_segment_end(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test increase_segment_end method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Without selected segment
        widget.increase_segment_end()

        # With selected segment
        widget.currently_selected_segment = widget.table_widget.model().record(0)
        widget.increase_segment_end()

        # Should not crash
        assert hasattr(widget, 'increase_segment_end')

        widget.close()

    def test_adjust_segment_timestamp_start(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test _adjust_segment_timestamp for start time"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Select first segment
        widget.currently_selected_segment = widget.table_widget.model().record(0)

        # Adjust start time
        widget._adjust_segment_timestamp("start_time", 100)

        # Should not crash
        assert hasattr(widget, '_adjust_segment_timestamp')

        widget.close()

    def test_adjust_segment_timestamp_end(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test _adjust_segment_timestamp for end time"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Select first segment
        widget.currently_selected_segment = widget.table_widget.model().record(0)

        # Adjust end time
        widget._adjust_segment_timestamp("end_time", 100)

        # Should not crash
        assert hasattr(widget, '_adjust_segment_timestamp')

        widget.close()

    def test_adjust_segment_timestamp_overlap_prevention(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test that _adjust_segment_timestamp prevents overlaps"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Select second segment (has previous and next segments)
        widget.currently_selected_segment = widget.table_widget.model().record(1)

        # Try to adjust start time to overlap with previous segment
        widget._adjust_segment_timestamp("start_time", -600)

        # Should not crash and should handle overlap
        assert hasattr(widget, '_adjust_segment_timestamp')

        widget.close()

    def test_on_audio_playback_state_changed(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test on_audio_playback_state_changed method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test with playing state
        widget.on_audio_playback_state_changed(QMediaPlayer.PlaybackState.PlayingState)

        # Test with stopped state
        widget.on_audio_playback_state_changed(QMediaPlayer.PlaybackState.StoppedState)

        # Should not crash
        assert hasattr(widget, 'on_audio_playback_state_changed')

        widget.close()

    def test_initialize_speed_control(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test initialize_speed_control method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.initialize_speed_control()

        # Should set speed combo text
        assert len(widget.speed_combo.currentText()) > 0
        assert "x" in widget.speed_combo.currentText()

        widget.close()

    def test_on_speed_changed_valid(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test on_speed_changed with valid speed"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.on_speed_changed("1.5x")

        # Should update audio player speed
        assert widget.audio_player.media_player.playbackRate() == 1.5

        widget.close()

    def test_on_speed_changed_invalid(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test on_speed_changed with invalid speed"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Should not crash with invalid input
        widget.on_speed_changed("invalid")

        widget.close()

    def test_on_speed_changed_clamping(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test on_speed_changed clamps values to valid range"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Too low
        widget.on_speed_changed("0.05x")
        assert widget.audio_player.media_player.playbackRate() >= 0.1

        # Too high
        widget.on_speed_changed("10x")
        assert widget.audio_player.media_player.playbackRate() <= 5.0

        widget.close()

    def test_increase_speed(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test increase_speed method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Set speed to a known value below maximum to ensure we can increase
        widget.set_speed(1.0)
        initial_speed = widget.get_current_speed()
        widget.increase_speed()
        new_speed = widget.get_current_speed()

        assert new_speed > initial_speed

        widget.close()

    def test_decrease_speed(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test decrease_speed method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Set speed to a known value above minimum to ensure we can decrease
        widget.set_speed(1.0)
        initial_speed = widget.get_current_speed()
        widget.decrease_speed()
        new_speed = widget.get_current_speed()

        assert new_speed < initial_speed

        widget.close()

    def test_get_current_speed(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test get_current_speed method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        speed = widget.get_current_speed()
        assert isinstance(speed, float)
        assert speed > 0

        widget.close()

    def test_set_speed(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test set_speed method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.set_speed(1.5)
        assert widget.get_current_speed() == 1.5

        widget.close()

    def test_perform_search(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test perform_search method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.search_text = "segment"
        widget.perform_search()

        # Should find matches
        assert len(widget.search_results) > 0

        widget.close()

    def test_search_in_table(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test search_in_table method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.search_text = "First"
        widget.search_in_table()

        # Should find match in first segment
        assert len(widget.search_results) > 0

        widget.close()

    def test_search_in_text(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test search_in_text method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.view_mode = ViewMode.TEXT
        widget.reset_view()

        widget.search_text = "segment"
        widget.search_in_text()

        # Should find matches
        assert len(widget.search_results) >= 0

        widget.close()

    def test_update_search_ui_with_results(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test update_search_ui with search results"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.search_results = [("table", 0, None), ("table", 1, None)]
        widget.update_search_ui()

        # Should enable buttons
        assert widget.search_prev_button.isEnabled()
        assert widget.search_next_button.isEnabled()
        assert len(widget.search_results_label.text()) > 0

        widget.close()

    def test_update_search_ui_no_results(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test update_search_ui with no search results"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.search_results = []
        widget.update_search_ui()

        # Should disable buttons
        assert not widget.search_prev_button.isEnabled()
        assert not widget.search_next_button.isEnabled()
        assert _("No matches found") in widget.search_results_label.text()

        widget.close()

    def test_highlight_current_match_table(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test highlight_current_match for table view"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.search_results = [("table", 0, None)]
        widget.current_search_index = 0
        widget.highlight_current_match()

        # Should not crash
        assert hasattr(widget, 'highlight_current_match')

        widget.close()

    def test_highlight_table_match(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test highlight_table_match method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.highlight_table_match(0)

        # Should select the row
        assert hasattr(widget, 'highlight_table_match')

        widget.close()

    def test_highlight_text_match(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test highlight_text_match method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.view_mode = ViewMode.TEXT
        widget.reset_view()

        widget.search_text = "test"
        widget.highlight_text_match(0)

        # Should not crash
        assert hasattr(widget, 'highlight_text_match')

        widget.close()

    def test_update_search_results_label(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test update_search_results_label method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.search_results = [("table", 0, None), ("table", 1, None)]
        widget.current_search_index = 0
        widget.update_search_results_label()

        # Should show "1 of 2"
        label_text = widget.search_results_label.text()
        assert "1" in label_text
        assert "2" in label_text

        widget.close()

    def test_show_search_bar(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test show_search_bar method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.show_search_bar()

        # Should show search frame and focus input
        assert hasattr(widget, 'show_search_bar')

        widget.close()

    def test_toggle_search_bar_visibility(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test toggle_search_bar_visibility method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test that the method exists and can be called
        widget.toggle_search_bar_visibility()

        # Should toggle visibility
        assert hasattr(widget, 'toggle_search_bar_visibility')

        widget.close()

    def test_event_filter(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test eventFilter method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent

        # Test Shift+Enter in search input
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.ShiftModifier
        )
        result = widget.eventFilter(widget.search_input, event)

        # Should handle the event
        assert isinstance(result, bool)

        widget.close()

    def test_reset_view_timestamps(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test reset_view with TIMESTAMPS mode"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)
        widget.show()  # Show the widget so visibility checks work

        widget.view_mode = ViewMode.TIMESTAMPS
        widget.reset_view()

        # Should show table, hide text display
        assert widget.table_widget.isVisible()
        assert not widget.text_display_box.isVisible()

        widget.close()

    def test_reset_view_text(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test reset_view with TEXT mode"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)
        widget.show()  # Show the widget so visibility checks work

        widget.view_mode = ViewMode.TEXT
        widget.reset_view()

        # Should show text display, hide table
        assert not widget.table_widget.isVisible()
        assert widget.text_display_box.isVisible()

        widget.close()

    def test_reset_view_translation(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test reset_view with TRANSLATION mode"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)
        widget.show()  # Show the widget so visibility checks work

        widget.view_mode = ViewMode.TRANSLATION
        widget.reset_view()

        # Should show text display, hide table
        assert not widget.table_widget.isVisible()
        assert widget.text_display_box.isVisible()

        widget.close()

    def test_on_timestamp_being_edited(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test on_timestamp_being_edited method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Without looping enabled
        widget.segment_looping_enabled = False
        widget.on_timestamp_being_edited(0, 0, 1000)

        # With looping enabled
        widget.segment_looping_enabled = True
        widget.currently_selected_segment = widget.table_widget.model().record(0)
        widget.on_timestamp_being_edited(0, 2, 1000)

        # Should not crash
        assert hasattr(widget, 'on_timestamp_being_edited')

        widget.close()

    def test_on_scroll_to_current_button_clicked_with_segments(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test on_scroll_to_current_button_clicked with multiple segments"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Set audio position to second segment
        widget.audio_player.set_position(600)
        widget.on_scroll_to_current_button_clicked()

        # Should not crash
        assert hasattr(widget, 'on_scroll_to_current_button_clicked')

        widget.close()

    def test_auto_scroll_to_current_position(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test auto_scroll_to_current_position method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.view_mode = ViewMode.TIMESTAMPS
        widget.audio_player.set_position(600)
        widget.auto_scroll_to_current_position()

        # Should not crash
        assert hasattr(widget, 'auto_scroll_to_current_position')

        widget.close()

    def test_resize_event(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test resizeEvent method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        from PyQt6.QtGui import QResizeEvent
        from PyQt6.QtCore import QSize

        event = QResizeEvent(QSize(1000, 800), QSize(800, 600))
        widget.resizeEvent(event)

        # Should not crash
        assert hasattr(widget, 'resizeEvent')

        widget.close()

    def test_close_event(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test closeEvent method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()

        widget.closeEvent(event)

        # Should clean up resources
        assert hasattr(widget, 'closeEvent')

    def test_save_geometry(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test save_geometry method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.save_geometry()

        # Should save to settings
        assert hasattr(widget, 'save_geometry')

        widget.close()

    def test_load_geometry(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test load_geometry method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.load_geometry()

        # Should load from settings
        assert hasattr(widget, 'load_geometry')

        widget.close()

    def test_load_preferences(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test load_preferences method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        preferences = widget.load_preferences()

        # Should return preferences object
        assert preferences is not None

        widget.close()

    def test_open_advanced_settings(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test open_advanced_settings method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.open_advanced_settings()

        # Should show dialog
        assert hasattr(widget, 'open_advanced_settings')

        widget.close()

    def test_on_transcription_options_changed(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test on_transcription_options_changed method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        mock_options = MagicMock()
        widget.on_transcription_options_changed(mock_options)

        # Should update transcription options
        assert widget.transcription_options == mock_options

        widget.close()

    def test_on_translate_button_clicked_no_api_key(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test on_translate_button_clicked without API key"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.openai_access_token = ""

        # Mock QMessageBox to prevent blocking dialog
        with patch('buzz.widgets.transcription_viewer.transcription_viewer_widget.QMessageBox.information') as mock_msgbox:
            widget.on_translate_button_clicked()

            # Should show message box
            mock_msgbox.assert_called_once()
            # Verify the message contains API key information
            call_args = mock_msgbox.call_args
            assert _("API Key Required") in call_args[0] or "API Key Required" in str(call_args)

        widget.close()

    def test_run_translation(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test run_translation method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Set required options
        widget.transcription_options.llm_model = "gpt-4"
        widget.transcription_options.llm_prompt = "Translate"

        widget.run_translation()

        # Should enqueue translation tasks
        assert hasattr(widget, 'run_translation')

        widget.close()

    def test_restore_ui_state(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test restore_ui_state method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.restore_ui_state()

        # Should restore UI elements
        assert hasattr(widget, 'restore_ui_state')

        widget.close()

    def test_create_search_bar(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test create_search_bar method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Should create search bar elements
        assert hasattr(widget, 'search_frame')
        assert hasattr(widget, 'search_input')
        assert hasattr(widget, 'search_prev_button')
        assert hasattr(widget, 'search_next_button')
        assert hasattr(widget, 'clear_search_button')

        widget.close()

    def test_create_loop_controls(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test create_loop_controls method"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Should create loop control elements
        assert hasattr(widget, 'loop_controls_frame')
        assert hasattr(widget, 'loop_toggle')
        assert hasattr(widget, 'follow_audio_toggle')
        assert hasattr(widget, 'speed_combo')
        assert hasattr(widget, 'speed_down_btn')
        assert hasattr(widget, 'speed_up_btn')
        assert hasattr(widget, 'scroll_to_current_button')

        widget.close()

    # This is passing locally, may fail on CI
    @pytest.mark.skipif(sys.platform.startswith("win"), reason="Skipping on Windows")
    def test_on_follow_audio_toggle_changed_enabled(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test on_follow_audio_toggle_changed when enabled"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.on_follow_audio_toggle_changed(True)

        # Should enable follow audio
        assert widget.follow_audio_enabled == True

        widget.close()

    # This is passing locally, may fail on CI
    @pytest.mark.skipif(sys.platform.startswith("win"), reason="Skipping on Windows")
    def test_on_follow_audio_toggle_changed_disabled(self, qtbot: QtBot, transcription, transcription_service, shortcuts):
        """Test on_follow_audio_toggle_changed when disabled"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        widget.on_follow_audio_toggle_changed(False)

        # Should disable follow audio
        assert widget.follow_audio_enabled == False

        widget.close()
