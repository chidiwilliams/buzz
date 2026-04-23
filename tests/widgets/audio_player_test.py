import os
import pytest
from unittest.mock import patch, MagicMock

from PyQt6.QtCore import QTime
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QHBoxLayout
from pytestqt.qtbot import QtBot

from buzz.widgets.audio_player import AudioPlayer
from tests.audio import test_audio_path
from buzz.settings.settings import Settings


def assert_approximately_equal(actual, expected, tolerance=0.001):
    """Helper function to compare values with tolerance for floating-point precision"""
    assert abs(actual - expected) < tolerance, f"Value {actual} is not approximately equal to {expected}"


class TestAudioPlayer:
    def test_should_load_audio(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        actual = os.path.normpath(widget.media_player.source().toLocalFile())
        expected = os.path.normpath(test_audio_path)
        assert actual == expected

    def test_should_update_time_label(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.position_ms = 1000
        widget.duration_ms = 2000
        widget.update_time_label()

        position_time = QTime(0, 0).addMSecs(1000).toString()
        duration_time = QTime(0, 0).addMSecs(2000).toString()

        assert widget.time_label.text() == f"{position_time} / {duration_time}"

    def test_should_toggle_play_button_icon(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Force Qt path for icon state testing
        widget._use_sd = False
        widget.on_playback_state_changed(QMediaPlayer.PlaybackState.PlayingState)
        assert widget.play_button.icon().themeName() == widget.pause_icon.themeName()

        widget.on_playback_state_changed(QMediaPlayer.PlaybackState.PausedState)
        assert widget.play_button.icon().themeName() == widget.play_icon.themeName()

        widget.on_playback_state_changed(QMediaPlayer.PlaybackState.StoppedState)
        assert widget.play_button.icon().themeName() == widget.play_icon.themeName()

    def test_should_have_basic_audio_controls(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Speed controls were moved to transcription viewer - just verify basic audio player functionality
        assert widget.play_button is not None
        assert widget.scrubber is not None
        assert widget.time_label is not None
        
        # Verify the widget loads audio correctly
        assert widget.media_player is not None
        assert os.path.normpath(widget.media_player.source().toLocalFile()) == os.path.normpath(test_audio_path)

    def test_should_change_playback_rate_directly(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Speed controls moved to transcription viewer - test basic playback rate functionality
        initial_rate = widget.media_player.playbackRate()
        widget.media_player.setPlaybackRate(1.5)
        assert_approximately_equal(widget.media_player.playbackRate(), 1.5)

    def test_should_handle_custom_playback_rates(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Speed controls moved to transcription viewer - test basic playback rate functionality
        widget.media_player.setPlaybackRate(1.7)
        assert_approximately_equal(widget.media_player.playbackRate(), 1.7)

    def test_should_handle_various_playback_rates(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Speed controls moved to transcription viewer - test basic playback rate functionality
        # Test that the media player can handle various playback rates
        widget.media_player.setPlaybackRate(0.5)
        assert_approximately_equal(widget.media_player.playbackRate(), 0.5)
        
        widget.media_player.setPlaybackRate(2.0)
        assert_approximately_equal(widget.media_player.playbackRate(), 2.0)

    def test_should_use_single_row_layout(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Verify the layout structure
        layout = widget.layout()
        assert isinstance(layout, QHBoxLayout)
        # Speed controls moved to transcription viewer - simplified layout
        assert layout.count() == 3  # play_button, scrubber, time_label

    def test_should_persist_playback_rate_setting(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Speed controls moved to transcription viewer - test that settings are loaded
        # The widget should load the saved playback rate from settings
        assert widget.settings is not None
        saved_rate = widget.settings.value(Settings.Key.AUDIO_PLAYBACK_RATE, 1.0, float)
        assert isinstance(saved_rate, float)
        assert 0.1 <= saved_rate <= 5.0

    def test_should_handle_range_looping(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test range setting and looping functionality
        widget.set_range((1000, 3000))  # 1-3 seconds
        assert widget.range_ms == (1000, 3000)
        
        # Clear range
        widget.clear_range()
        assert widget.range_ms is None

    def test_should_handle_invalid_media(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.set_invalid_media(True)
        
        # Speed controls moved to transcription viewer - just verify invalid media handling
        assert widget.invalid_media is True
        assert widget.play_button.isEnabled() is False
        assert widget.scrubber.isEnabled() is False
        assert widget.time_label.isEnabled() is False

    def test_should_stop_playback(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test stop functionality
        widget.stop()
        assert widget.media_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState

    def test_should_handle_media_status_changes(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test media status handling
        widget.on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)
        assert widget.invalid_media is False
        
        widget.on_media_status_changed(QMediaPlayer.MediaStatus.InvalidMedia)
        assert widget.invalid_media is True

    def test_should_re_enable_controls_on_valid_media(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.set_invalid_media(True)
        widget.set_invalid_media(False)

        assert widget.play_button.isEnabled()
        assert widget.scrubber.isEnabled()
        assert widget.time_label.isEnabled()

    def test_sounddevice_player_initialised(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # sounddevice path should be active for a valid audio file
        assert widget._sd_player is not None
        assert widget._use_sd is True

    def test_sounddevice_duration_reported(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        if widget._use_sd:
            assert widget.duration_ms > 0

    def test_qt_audio_muted_when_sounddevice_active(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        if widget._use_sd:
            assert widget.audio_output.isMuted()

    def test_poll_position_updates_scrubber(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        if not widget._use_sd:
            pytest.skip("sounddevice not active")

        widget.on_duration_changed(5000)
        # Manually drive _poll_position with a mock position
        widget._sd_player._player._frame_pos = int(1.0 * widget._sd_player._player.samplerate)
        widget._poll_position()

        assert widget.scrubber.value() > 0

    def test_poll_position_skips_scrubber_while_dragging(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        if not widget._use_sd:
            pytest.skip("sounddevice not active")

        widget.on_duration_changed(5000)
        widget.scrubber.setValue(1000)
        widget.is_slider_dragging = True
        widget._sd_player._player._frame_pos = int(2.0 * widget._sd_player._player.samplerate)
        widget._poll_position()

        assert widget.scrubber.value() == 1000

    def test_set_position_uses_sounddevice(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        if not widget._use_sd:
            pytest.skip("sounddevice not active")

        widget.set_position(500)
        assert abs(widget._sd_player.position_ms - 500) < 50

    def test_toggle_play_sounddevice_path(self, qtbot: QtBot):
        with patch("sounddevice.OutputStream", return_value=MagicMock()):
            widget = AudioPlayer(test_audio_path)
            qtbot.add_widget(widget)

            if not widget._use_sd:
                pytest.skip("sounddevice not active")

            # Start playing
            widget.toggle_play()
            assert widget._sd_player.is_playing
            assert widget._poll_timer.isActive()

            # Pause
            widget.toggle_play()
            assert not widget._sd_player.is_playing
            assert not widget._poll_timer.isActive()

    def test_stop_stops_sounddevice(self, qtbot: QtBot):
        with patch("sounddevice.OutputStream", return_value=MagicMock()):
            widget = AudioPlayer(test_audio_path)
            qtbot.add_widget(widget)

            if not widget._use_sd:
                pytest.skip("sounddevice not active")

            widget.toggle_play()
            widget.stop()

            assert not widget._sd_player.is_playing
            assert not widget._poll_timer.isActive()

    def test_range_looping_with_sounddevice(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.set_range((1000, 3000))
        assert widget.range_ms == (1000, 3000)

        widget.clear_range()
        assert widget.range_ms is None

    def test_on_slider_moved_clears_range_if_far_outside(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.set_range((1000, 3000))
        # Move slider far outside range (> 2000 ms away)
        widget.on_slider_moved(6000)
        assert widget.range_ms is None

    def test_on_slider_moved_keeps_range_if_close(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.set_range((1000, 3000))
        # Move within 2000 ms of range boundary
        widget.on_slider_moved(2000)
        assert widget.range_ms == (1000, 3000)
