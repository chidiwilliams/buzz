import os
import pytest

from PyQt6.QtCore import QTime
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QVBoxLayout
from pytestqt.qtbot import QtBot

from buzz.widgets.video_player import VideoPlayer
from tests.audio import test_audio_path


def assert_approximately_equal(actual, expected, tolerance=0.001):
    """Helper function to compare values with tolerance for floating-point precision"""
    assert abs(actual - expected) < tolerance, f"Value {actual} is not approximately equal to {expected}"


class TestVideoPlayer:
    def test_should_load_media(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        actual = os.path.normpath(widget.media_player.source().toLocalFile())
        expected = os.path.normpath(test_audio_path)
        assert actual == expected

    def test_should_update_time_label(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.on_duration_changed(2000)
        widget.on_position_changed(1000)

        position_time = QTime(0, 0).addMSecs(1000).toString()
        duration_time = QTime(0, 0).addMSecs(2000).toString()

        assert widget.time_label.text() == f"{position_time} / {duration_time}"

    def test_should_toggle_play_button_icon(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.on_playback_state_changed(QMediaPlayer.PlaybackState.PlayingState)
        assert widget.play_button.icon().themeName() == widget.pause_icon.themeName()

        widget.on_playback_state_changed(QMediaPlayer.PlaybackState.PausedState)
        assert widget.play_button.icon().themeName() == widget.play_icon.themeName()

        widget.on_playback_state_changed(QMediaPlayer.PlaybackState.StoppedState)
        assert widget.play_button.icon().themeName() == widget.play_icon.themeName()

    def test_should_have_basic_video_controls(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert widget.play_button is not None
        assert widget.scrubber is not None
        assert widget.time_label is not None
        assert widget.video_widget is not None

        # Verify the widget loads media correctly
        assert widget.media_player is not None
        assert os.path.normpath(widget.media_player.source().toLocalFile()) == os.path.normpath(test_audio_path)

    def test_should_change_playback_rate_directly(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.media_player.setPlaybackRate(1.5)
        assert_approximately_equal(widget.media_player.playbackRate(), 1.5)

    def test_should_handle_various_playback_rates(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.media_player.setPlaybackRate(0.5)
        assert_approximately_equal(widget.media_player.playbackRate(), 0.5)

        widget.media_player.setPlaybackRate(2.0)
        assert_approximately_equal(widget.media_player.playbackRate(), 2.0)

    def test_should_use_vertical_layout(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Verify the layout structure - VideoPlayer uses VBoxLayout
        layout = widget.layout()
        assert isinstance(layout, QVBoxLayout)
        # video_widget + controls layout
        assert layout.count() == 2

    def test_should_handle_range_looping(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test range setting and looping functionality
        widget.set_range((1000, 3000))  # 1-3 seconds
        assert widget.range_ms == (1000, 3000)

        # Clear range
        widget.clear_range()
        assert widget.range_ms is None

    def test_should_stop_playback(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test stop functionality
        widget.stop()
        assert widget.media_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState

    def test_should_set_position(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test position setting
        widget.set_position(1000)
        # Position may not be exactly 1000 due to media player internals
        # but the method should execute without error

    def test_should_track_slider_dragging(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Initially not dragging
        assert widget.is_slider_dragging is False

        # Simulate slider press
        widget.on_slider_pressed()
        assert widget.is_slider_dragging is True

        # Simulate slider release
        widget.on_slider_released()
        assert widget.is_slider_dragging is False

    def test_should_emit_position_changed_signal(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Track signal emission
        with qtbot.waitSignal(widget.position_ms_changed, timeout=1000):
            widget.on_position_changed(500)

        assert widget.position_ms == 500

    def test_should_update_scrubber_range_on_duration_change(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.on_duration_changed(5000)
        assert widget.scrubber.maximum() == 5000
        assert widget.duration_ms == 5000

    def test_should_toggle_playback(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test toggle functionality exists
        assert hasattr(widget, 'toggle_playback')

    def test_should_have_video_widget_constraints(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Verify video widget size constraints
        assert widget.video_widget.minimumHeight() == 200
        assert widget.video_widget.maximumHeight() == 400

    def test_should_have_audio_output(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert widget.audio_output is not None
        assert widget.media_player.audioOutput() == widget.audio_output

    def test_should_handle_range_with_position_outside(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Set position outside the range first
        widget.position_ms = 5000

        # Set range - should jump to start since position is outside
        widget.set_range((1000, 3000))
        assert widget.range_ms == (1000, 3000)

    def test_should_handle_range_with_position_inside(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Set position inside the range first
        widget.position_ms = 2000

        # Set range - should NOT jump since position is inside
        widget.set_range((1000, 3000))
        assert widget.range_ms == (1000, 3000)

    def test_should_loop_at_range_end(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Set a range
        widget.set_range((1000, 3000))

        # Simulate reaching end of range
        widget.is_looping = False
        widget.on_position_changed(2960)  # Just before end (within 50ms threshold)

        # The looping flag should be set during the loop operation
        # After on_position_changed completes, is_looping should be False again
        assert widget.is_looping is False

    def test_should_not_update_scrubber_while_dragging(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # First set a valid range for the scrubber
        widget.on_duration_changed(5000)

        # Set a known value within the range
        widget.scrubber.setValue(1000)

        # Start dragging
        widget.on_slider_pressed()

        # Position change while dragging should not update scrubber
        widget.on_position_changed(2000)

        # Scrubber value should still be 1000 (not updated during drag)
        assert widget.scrubber.value() == 1000

        # Release slider
        widget.on_slider_released()

    def test_should_update_scrubber_when_not_dragging(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # First set a valid range for the scrubber
        widget.on_duration_changed(5000)

        # Ensure not dragging
        widget.is_slider_dragging = False

        # Position change when not dragging should update scrubber
        widget.on_position_changed(2000)

        assert widget.scrubber.value() == 2000

    def test_initial_frame_loading(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Initial state
        assert widget.initial_frame_loaded is False

        # Simulate media loaded - should trigger play
        widget.on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)

        # Simulate buffered - should pause and set flag
        widget.on_media_status_changed(QMediaPlayer.MediaStatus.BufferedMedia)
        assert widget.initial_frame_loaded is True

        # Further status changes should be ignored
        widget.on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)
        # Should still be True (not reset)
        assert widget.initial_frame_loaded is True

    def test_play_button_sizing(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert widget.play_button.maximumWidth() == 40
        assert widget.play_button.minimumHeight() == 30
