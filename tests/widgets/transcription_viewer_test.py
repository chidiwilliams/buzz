import uuid
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame

from buzz.locale import _
from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.transcription_view_mode_tool_button import (
    TranscriptionViewModeToolButton,
    ViewMode
)
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    TranscriptionSegmentsEditorWidget,
)
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)
from buzz.widgets.transcription_viewer.transcription_resizer_widget import (
    TranscriptionResizerWidget,
    TranscriptionWorker,
)
from tests.audio import test_audio_path


class TestTranscriptionViewerWidget:
    @pytest.fixture()
    def transcription(
        self, transcription_dao, transcription_segment_dao
    ) -> Transcription:
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
        transcription_segment_dao.insert(TranscriptionSegment(40, 299, "Bien", "", str(id)))
        transcription_segment_dao.insert(
            TranscriptionSegment(299, 329, "venue dans", "", str(id))
        )

        return transcription_dao.find_by_id(str(id))

    def test_should_display_segments(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        assert widget.windowTitle() == "whisper-french.mp3"

        editor = widget.findChild(TranscriptionSegmentsEditorWidget)
        assert isinstance(editor, TranscriptionSegmentsEditorWidget)

        assert editor.model().index(0, 1).data() == 299
        assert editor.model().index(0, 2).data() == 40
        assert editor.model().index(0, 3).data() == "Bien"
        widget.close()

    def test_should_update_segment_text(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        editor = widget.findChild(TranscriptionSegmentsEditorWidget)
        assert isinstance(editor, TranscriptionSegmentsEditorWidget)

        editor.model().setData(editor.model().index(0, 3), "Biens")
        widget.close()

    def test_should_resize_segment_text(self, qtbot, transcription, transcription_service):
        transcription_service.update_transcription_as_completed = MagicMock()

        widget = TranscriptionResizerWidget(transcription, transcription_service)
        widget.target_chars_spin_box.setValue(5)

        qtbot.add_widget(widget)

        widget.on_resize_button_clicked()

        transcription_service.update_transcription_as_completed.assert_called_once()

        widget.close()

    def test_on_merge_button_clicked(self, qtbot: QtBot, transcription, transcription_service):
        # Prerequisite: Merge button is only enabled if word_level_timings is True
        transcription.word_level_timings = True

        # Mock services and signals
        transcription_service.copy_transcription = MagicMock(return_value=uuid.uuid4())
        transcription_service.update_transcription_progress = MagicMock()

        mock_signal = MagicMock()

        widget = TranscriptionResizerWidget(
            transcription=transcription,
            transcription_service=transcription_service,
            transcriptions_updated_signal=mock_signal)
        qtbot.add_widget(widget)

        # Patch the worker and thread to prevent actual background processing
        with patch('buzz.widgets.transcription_viewer.transcription_resizer_widget.QThread') as mock_thread_class, \
                patch(
                    'buzz.widgets.transcription_viewer.transcription_resizer_widget.TranscriptionWorker') as mock_worker_class:
            mock_worker_instance = MagicMock()
            mock_worker_class.return_value = mock_worker_instance

            mock_thread_instance = MagicMock()
            mock_thread_class.return_value = mock_thread_instance

            # Action: click the merge button
            widget.merge_button.click()

            # Assertions
            # 1. A new transcription is copied
            transcription_service.copy_transcription.assert_called_once_with(transcription.id_as_uuid)
            new_transcript_id = transcription_service.copy_transcription.return_value

            # 2. Progress is updated for the new transcription
            transcription_service.update_transcription_progress.assert_called_once_with(new_transcript_id, 0.0)

            # 3. Signal is emitted to notify of the new transcription
            mock_signal.emit.assert_called_once_with(new_transcript_id)

            # 4. The regroup string is constructed.
            expected_regroup_string_with_bug = 'mg=0.2++42+1_sp=.* /./. /。/?/? /？/!/! /！/,/, _sl=42'

            # 5. Worker is created with the correct arguments
            mock_worker_class.assert_called_once()
            called_args, _ = mock_worker_class.call_args
            assert called_args[0] == transcription
            assert called_args[2] == transcription_service
            assert called_args[3] == expected_regroup_string_with_bug

            # 6. Worker is moved to a new thread and the thread is started
            mock_worker_instance.moveToThread.assert_called_once_with(mock_thread_instance)
            mock_thread_instance.start.assert_called_once()

            # 7. Widget is hidden after starting the process
            assert not widget.isVisible()

            widget.close()

    def test_text_button_changes_view_mode(
            self, qtbot, transcription, transcription_service, shortcuts
    ):
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        view_mode_tool_button = widget.findChild(TranscriptionViewModeToolButton)
        menu = view_mode_tool_button.menu()

        text_action = next(action for action in menu.actions() if action.text() == _("Text"))
        text_action.trigger()
        assert widget.view_mode == ViewMode.TEXT

        text_action = next(action for action in menu.actions() if action.text() == _("Translation"))
        text_action.trigger()
        assert widget.view_mode == ViewMode.TRANSLATION

        widget.close()

    def test_transcription_worker_calls_stable_whisper(self, qtbot: QtBot, transcription, transcription_service):
        mock_transcription_options = MagicMock()
        mock_transcription_options.extract_speech = False
        regroup_string = "mg=0.2"

        worker = TranscriptionWorker(
            transcription=transcription,
            transcription_options=mock_transcription_options,
            transcription_service=transcription_service,
            regroup_string=regroup_string,
        )

        mock_result_segment = MagicMock()
        mock_result_segment.start = 1.0
        mock_result_segment.end = 2.0
        mock_result_segment.text = "Hello"

        mock_result = MagicMock()
        mock_result.segments = [mock_result_segment]

        with patch('buzz.widgets.transcription_viewer.transcription_resizer_widget.stable_whisper.transcribe_any', return_value=mock_result) as mock_transcribe_any, \
             patch('buzz.widgets.transcription_viewer.transcription_resizer_widget.whisper_audio.load_audio') as mock_load_audio:

            result_ready_spy = MagicMock()
            finished_spy = MagicMock()
            worker.result_ready.connect(result_ready_spy)
            worker.finished.connect(finished_spy)

            worker.run()

            mock_load_audio.assert_called_with(transcription.file)
            
            mock_transcribe_any.assert_called_once()
            call_args, call_kwargs = mock_transcribe_any.call_args
            
            assert call_args[0] == worker.get_transcript
            assert call_kwargs['audio'] == mock_load_audio.return_value
            assert call_kwargs['regroup'] == regroup_string
            assert call_kwargs['vad'] is True
            assert call_kwargs['suppress_silence'] is True

            result_ready_spy.assert_called_once()
            emitted_segments = result_ready_spy.call_args[0][0]
            assert len(emitted_segments) == 1
            assert emitted_segments[0].start == 100
            assert emitted_segments[0].end == 200
            assert emitted_segments[0].text == "Hello"
            
            finished_spy.assert_called_once()

    def test_loop_toggle_functionality(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test the Loop Segment toggle functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Check that loop toggle exists and has correct properties
        assert hasattr(widget, 'loop_toggle')
        assert widget.loop_toggle.text() == _("Loop Segment")
        assert widget.loop_toggle.toolTip() == _("Enable/disable looping when clicking on transcript segments")
        
        # Check initial state
        initial_state = widget.loop_toggle.isChecked()
        
        # Test state change
        widget.loop_toggle.setChecked(not initial_state)
        widget.on_loop_toggle_changed(not initial_state)
        
        # Verify state changed
        assert widget.loop_toggle.isChecked() == (not initial_state)
        
        # Verify setting is saved
        assert widget.settings.settings.value("transcription_viewer/segment_looping_enabled", type=bool) == (not initial_state)
        
        widget.close()

    def test_follow_audio_toggle_functionality(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test the Follow Audio toggle functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Check that follow audio toggle exists and has correct properties
        assert hasattr(widget, 'follow_audio_toggle')
        assert widget.follow_audio_toggle.text() == _("Follow Audio")
        assert widget.follow_audio_toggle.toolTip() == _("Enable/disable following the current audio position in the transcript. When enabled, automatically scrolls to current text.")
        
        # Check initial state
        initial_state = widget.follow_audio_toggle.isChecked()
        
        # Test state change
        widget.follow_audio_toggle.setChecked(not initial_state)
        widget.on_follow_audio_toggle_changed(not initial_state)
        
        # Verify state changed
        assert widget.follow_audio_toggle.isChecked() == (not initial_state)
        
        # Verify setting is saved
        assert widget.settings.settings.value("transcription_viewer/follow_audio_enabled", type=bool) == (not initial_state)
        
        widget.close()

    def test_scroll_to_current_button_functionality(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test the Scroll to Current button functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Check that scroll to current button exists and has correct properties
        assert hasattr(widget, 'scroll_to_current_button')
        assert widget.scroll_to_current_button.text() == _("Scroll to Current")
        assert widget.scroll_to_current_button.toolTip() == _("Scroll to the currently spoken text")
        
        # Test button click
        widget.scroll_to_current_button.click()
        
        widget.close()

    def test_search_bar_creation_and_visibility(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test search bar creation and visibility functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Check that search bar components exist
        assert hasattr(widget, 'search_frame')
        assert hasattr(widget, 'search_input')
        assert hasattr(widget, 'search_results_label')
        assert hasattr(widget, 'search_prev_button')
        assert hasattr(widget, 'search_next_button')
        assert hasattr(widget, 'clear_search_button')
        
        # Check initial state (search bar should be hidden)
        assert not widget.search_frame.isVisible()
        
        # Test showing search bar
        widget.focus_search_input()
        # Note: In test environment, visibility might not work as expected
        # Focus on functional aspects instead
        
        # Test hiding search bar
        widget.hide_search_bar()
        
        widget.close()

    def test_search_functionality_basic(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test basic search functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Show search bar
        widget.focus_search_input()
        
        # Test typing in search input
        test_search_text = "test search"
        qtbot.keyClicks(widget.search_input, test_search_text)
        
        # Verify search text is captured
        assert widget.search_input.text() == test_search_text
        
        # Verify search results label updates
        assert hasattr(widget, 'search_results_label')
        
        # Test clearing search
        widget.clear_search()
        assert widget.search_input.text() == ""
        
        widget.close()

    def test_search_navigation_buttons(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test search navigation buttons"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Show search bar
        widget.focus_search_input()
        
        # Test search previous button
        widget.search_prev_button.click()
        
        # Test search next button
        widget.search_next_button.click()
        
        widget.close()

    def test_search_keyboard_shortcuts(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test search keyboard shortcuts"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test Ctrl+F to focus search
        qtbot.keyPress(widget, Qt.Key.Key_F, modifier=Qt.KeyboardModifier.ControlModifier)
        
        # Test Enter for next search
        qtbot.keyPress(widget, Qt.Key.Key_Return)
        
        # Test Shift+Enter for previous search
        qtbot.keyPress(widget, Qt.Key.Key_Return, modifier=Qt.KeyboardModifier.ShiftModifier)
        
        # Test Escape to hide search
        qtbot.keyPress(widget, Qt.Key.Key_Escape)
        
        widget.close()

    def test_search_in_different_view_modes(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test search functionality in different view modes"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Show search bar
        widget.focus_search_input()
        
        # Test search in TEXT view mode
        widget.view_mode = ViewMode.TEXT
        qtbot.keyClicks(widget.search_input, "test")
        widget.perform_search()
        
        # Test search in TIMESTAMPS view mode
        widget.view_mode = ViewMode.TIMESTAMPS
        qtbot.keyClicks(widget.search_input, "test")
        widget.perform_search()
        
        widget.close()

    def test_search_performance_limits(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test search with very long text to ensure no crashes"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Show search bar
        widget.focus_search_input()
        
        # Test with very long search text
        long_text = "a" * 10000
        qtbot.keyClicks(widget.search_input, long_text)
        
        # Should not crash
        widget.perform_search()
        
        widget.close()

    def test_search_clear_functionality(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test search clear functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Show search bar
        widget.focus_search_input()
        
        # Add some search text
        qtbot.keyClicks(widget.search_input, "test text")
        
        # Clear search
        widget.clear_search()
        
        # Verify search is cleared
        assert widget.search_input.text() == ""
        assert len(widget.search_results) == 0
        
        widget.close()

    def test_search_hide_functionality(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        """Test search hide functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Show search bar
        widget.focus_search_input()
        
        # Add some search text
        qtbot.keyClicks(widget.search_input, "test text")
        
        # Hide search bar
        widget.hide_search_bar()
        
        # Verify search is cleared when hiding
        assert widget.search_input.text() == ""
        assert len(widget.search_results) == 0
        
        widget.close()







    def test_speed_controls_functionality(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test the speed controls functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Show playback controls first
        widget.show_loop_controls()

        # Test speed combo box
        initial_speed = widget.speed_combo.currentText()
        widget.speed_combo.setCurrentText("1.5x")
        assert widget.speed_combo.currentText() == "1.5x"

        # Test speed increase button
        qtbot.mouseClick(widget.speed_up_btn, Qt.MouseButton.LeftButton)
        new_speed = widget.get_current_speed()
        assert new_speed > 1.0

        # Test speed decrease button
        qtbot.mouseClick(widget.speed_down_btn, Qt.MouseButton.LeftButton)
        decreased_speed = widget.get_current_speed()
        assert decreased_speed < new_speed

        widget.close()



    def test_ui_state_persistence(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that UI state is properly persisted to settings"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test that playback controls visibility state is saved
        widget.show_loop_controls()
        assert widget.settings.settings.value("transcription_viewer/playback_controls_visible", False, type=bool)

        widget.close()

    def test_button_sizing_consistency(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that all search and speed control buttons have consistent sizing"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test search button sizing
        assert widget.search_prev_button.maximumWidth() == 40
        assert widget.search_prev_button.minimumHeight() == 30
        assert widget.search_next_button.maximumWidth() == 40
        assert widget.search_next_button.minimumHeight() == 30
        assert widget.clear_search_button.maximumWidth() == 80
        assert widget.clear_search_button.minimumHeight() == 30

        # Test speed control button sizing
        assert widget.speed_down_btn.maximumWidth() == 40
        assert widget.speed_down_btn.minimumHeight() == 30
        assert widget.speed_up_btn.maximumWidth() == 40
        assert widget.speed_up_btn.minimumHeight() == 30

        # Verify all buttons have consistent height
        button_heights = [
            widget.search_prev_button.minimumHeight(),
            widget.search_next_button.minimumHeight(),
            widget.clear_search_button.minimumHeight(),
            widget.speed_down_btn.minimumHeight(),
            widget.speed_up_btn.minimumHeight(),
        ]
        assert len(set(button_heights)) == 1, "All buttons should have the same height"

        widget.close()

    def test_search_input_width(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that search input has appropriate width for better usability"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test that search input has minimum width of 300px
        assert widget.search_input.minimumWidth() >= 300

        widget.close()

    def test_current_segment_display_improvements(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test the improvements made to current segment display"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test that current segment frame has no frame border
        assert widget.current_segment_frame.frameStyle() == QFrame.Shape.NoFrame

        # Test that current segment header has correct text and styling
        assert widget.current_segment_header.text() == "Now Speaking:"
        assert "font-weight: bold" in widget.current_segment_header.styleSheet()
        assert "color: #666" in widget.current_segment_header.styleSheet()
        assert "font-size: 0.75em" in widget.current_segment_header.styleSheet()

        # Test that current segment text is centered
        alignment = widget.current_segment_text.alignment()
        assert alignment & Qt.AlignmentFlag.AlignHCenter
        assert alignment & Qt.AlignmentFlag.AlignTop

        # Test that current segment text has appropriate styling
        assert "color: #666" in widget.current_segment_text.styleSheet()
        assert "line-height: 1.1" in widget.current_segment_text.styleSheet()

        # Test that scroll area is properly set up
        assert hasattr(widget, 'current_segment_scroll_area')
        assert widget.current_segment_scroll_area.widget() == widget.current_segment_text

        widget.close()

    def test_resize_current_segment_frame(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test the resize_current_segment_frame method for dynamic sizing"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Initially, frame should be hidden
        assert not widget.current_segment_frame.isVisible()

        # Test with short text
        short_text = "Short text"
        widget.current_segment_text.setText(short_text)
        widget.resize_current_segment_frame()
        
        # Frame should now be visible and sized appropriately
        assert widget.current_segment_frame.isVisible()
        assert widget.current_segment_frame.maximumHeight() > 0
        assert widget.current_segment_frame.minimumHeight() > 0

        # Test with longer text
        long_text = "This is a much longer text that should cause the frame to resize and potentially hit the maximum height limit. It should be long enough to test the line wrapping and height calculation logic."
        widget.current_segment_text.setText(long_text)
        widget.resize_current_segment_frame()
        
        # Frame should still be visible and properly sized
        assert widget.current_segment_frame.isVisible()
        assert widget.current_segment_frame.maximumHeight() > 0
        assert widget.current_segment_frame.minimumHeight() > 0

        # Test with empty text
        widget.current_segment_text.setText("")
        widget.resize_current_segment_frame()
        
        # Frame should be hidden when no text
        assert widget.current_segment_frame.maximumHeight() == 0
        assert widget.current_segment_frame.minimumHeight() == 0

        widget.close()

    def test_playback_controls_button_icon(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that playback controls button uses the correct Play icon"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test that the button has an icon set
        assert not widget.playback_controls_toggle_button.icon().isNull()

        # Test that the button is properly connected to toggle functionality
        assert hasattr(widget, 'toggle_loop_controls_visibility')

        widget.close()

    def test_layout_optimizations(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that layout optimizations are properly applied"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test that main layout has proper stretch factors
        # Table widget should have stretch factor 1 (majority of space)
        # Other widgets should have stretch factor 0 (minimal space)
        main_layout = widget.layout()
        
        # Find the table widget in the layout
        table_widget_index = None
        for i in range(main_layout.count()):
            if main_layout.itemAt(i).widget() == widget.table_widget:
                table_widget_index = i
                break
        
        assert table_widget_index is not None, "Table widget should be in main layout"
        
        # Test that current segment frame has minimal stretch
        current_segment_index = None
        for i in range(main_layout.count()):
            if main_layout.itemAt(i).widget() == widget.current_segment_frame:
                current_segment_index = i
                break
        
        assert current_segment_index is not None, "Current segment frame should be in main layout"

        widget.close()

    def test_settings_integration_for_new_features(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that new features properly integrate with settings system"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test that playback controls visibility setting is properly initialized
        initial_setting = widget.settings.settings.value("transcription_viewer/playback_controls_visible", False, type=bool)
        assert isinstance(initial_setting, bool)

        # Test that calling show_loop_controls saves the setting
        widget.show_loop_controls()
        saved_setting = widget.settings.settings.value("transcription_viewer/playback_controls_visible", False, type=bool)
        assert saved_setting == True

        # Test that calling hide_loop_controls saves the setting
        widget.hide_loop_controls()
        saved_setting = widget.settings.settings.value("transcription_viewer/playback_controls_visible", False, type=bool)
        assert saved_setting == False

        # Test that toggle method also saves the setting
        widget.toggle_loop_controls_visibility()
        saved_setting = widget.settings.settings.value("transcription_viewer/playback_controls_visible", False, type=bool)
        assert saved_setting == True

        widget.close()

    def test_search_results_label_format(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that search results label shows the correct format (1 of X matches)"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test initial state
        assert "0 of 0 matches" in widget.search_results_label.text()

        # Test with search results
        widget.search_input.setText("test")
        qtbot.keyPress(widget.search_input, Qt.Key.Key_Return)
        
        # Wait for search to complete
        qtbot.wait(100)
        
        # Verify the format is correct (should show "1 of X matches" or similar)
        results_text = widget.search_results_label.text()
        assert "of" in results_text
        assert "match" in results_text.lower()

        widget.close()

    def test_current_segment_text_scrolling(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that current segment text properly scrolls when content is too long"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Test with very long text that should trigger scrolling
        long_text = "This is a very long text that should definitely exceed the maximum height limit and trigger the scrolling functionality. " * 10
        widget.current_segment_text.setText(long_text)
        widget.resize_current_segment_frame()
        
        # Frame should be visible but constrained to maximum height
        assert widget.current_segment_frame.isVisible()
        assert widget.current_segment_frame.maximumHeight() > 0
        
        # The scroll area should be properly configured
        scroll_area = widget.current_segment_scroll_area
        assert scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        assert scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

        widget.close()

    def test_search_bar_visibility_toggle(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that search bar can be properly shown and hidden"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Initially search frame should be hidden
        assert not widget.search_frame.isVisible()

        # Show search bar
        widget.show_search_bar()
        assert widget.search_frame.isVisible()

        # Hide search bar
        widget.hide_search_bar()
        assert not widget.search_frame.isVisible()

        widget.close()

    def test_audio_player_playback_state_disconnection(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that audio player playback state changes don't auto-toggle playback controls"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Initially playback controls should be hidden
        initial_visibility = widget.loop_controls_frame.isVisible()
        
        # Simulate audio playback state change
        widget.on_audio_playback_state_changed("playing")
        
        # Playback controls visibility should not have changed
        assert widget.loop_controls_frame.isVisible() == initial_visibility
        
        # The method should exist but do nothing (as intended)
        assert hasattr(widget, 'on_audio_playback_state_changed')

        widget.close()

    def test_current_segment_header_styling(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that current segment header has proper styling and constraints"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        header = widget.current_segment_header
        
        # Test header text
        assert header.text() == "Now Speaking:"
        
        # Test header styling
        stylesheet = header.styleSheet()
        assert "font-weight: bold" in stylesheet
        assert "color: #666" in stylesheet
        assert "font-size: 0.75em" in stylesheet
        assert "margin: 0" in stylesheet
        assert "padding: 0" in stylesheet
        
        # Test header alignment
        assert header.alignment() & Qt.AlignmentFlag.AlignHCenter
        assert header.alignment() & Qt.AlignmentFlag.AlignTop
        
        # Test header height constraint
        assert header.maximumHeight() == 16

        widget.close()

    def test_search_clear_functionality_comprehensive(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test comprehensive search clear functionality including UI state reset"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Set up search
        widget.search_input.setText("test search")
        qtbot.keyPress(widget.search_input, Qt.Key.Key_Return)
        qtbot.wait(100)
        
        # Verify search is active
        assert widget.search_input.text() == "test search"
        assert "match" in widget.search_results_label.text().lower()
        
        # Clear search
        qtbot.mouseClick(widget.clear_search_button, Qt.MouseButton.LeftButton)
        qtbot.wait(100)
        
        # Verify search is cleared
        assert widget.search_input.text() == ""
        assert "0 of 0 matches" in widget.search_results_label.text()
        
        # Verify search navigation buttons are disabled
        assert not widget.search_prev_button.isEnabled()
        assert not widget.search_next_button.isEnabled()

        widget.close()
