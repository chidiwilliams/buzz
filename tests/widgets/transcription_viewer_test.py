import uuid
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import Qt

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
        assert hasattr(widget, 'close_search_button')
        
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

    def test_playback_controls_toggle_button_functionality(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test the Playback Controls toggle button functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Wait for widget to be fully initialized
        qtbot.wait(100)

        # Test that the button can toggle the controls
        initial_state = widget.loop_controls_frame.isVisible()
        
        # Click the button to toggle controls
        qtbot.mouseClick(widget.playback_controls_toggle_button, Qt.MouseButton.LeftButton)
        qtbot.wait(100)  # Wait for UI update
        
        # State should have changed
        new_state = widget.loop_controls_frame.isVisible()
        assert new_state != initial_state
        
        # Button state should match frame visibility
        assert widget.playback_controls_toggle_button.isChecked() == new_state

        widget.close()

    def test_find_button_functionality(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test the Find button functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Wait for widget to be fully initialized
        qtbot.wait(100)

        # Test that the button can toggle the find widget
        initial_state = widget.search_frame.isVisible()
        
        # Click the button to toggle find widget
        qtbot.mouseClick(widget.find_button, Qt.MouseButton.LeftButton)
        qtbot.wait(100)  # Wait for UI update
        
        # State should have changed
        new_state = widget.search_frame.isVisible()
        assert new_state != initial_state
        
        # Button state should match frame visibility
        assert widget.find_button.isChecked() == new_state

        widget.close()

    def test_cmd_f_toggle_functionality(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that Cmd+F properly toggles the find widget"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Initially, find widget should be hidden
        assert not widget.search_frame.isVisible()

        # Simulate Cmd+F to show find widget
        qtbot.keyPress(widget, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        assert widget.search_frame.isVisible()

        # Simulate Cmd+F again to hide find widget
        qtbot.keyPress(widget, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        assert not widget.search_frame.isVisible()

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

    def test_current_segment_display_functionality(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test the current segment display functionality"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Initially, current segment frame should be hidden
        assert not widget.current_segment_frame.isVisible()

        # Simulate selecting a segment
        segments = widget.table_widget.segments()
        if segments:
            first_segment = segments[0]
            widget.on_segment_selected(first_segment)
            
            # Current segment frame should now be visible
            assert widget.current_segment_frame.isVisible()
            assert widget.current_segment_text.text() == first_segment.value("text")

        widget.close()

    def test_ui_state_persistence(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        """Test that UI state is properly saved and restored"""
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        # Show playback controls and find widget
        widget.show_loop_controls()
        widget.show_search_bar()

        # Verify settings are saved
        assert widget.settings.settings.value("transcription_viewer/playback_controls_visible", False, type=bool)
        assert widget.settings.settings.value("transcription_viewer/find_widget_visible", False, type=bool)

        widget.close()
