import os
import pytest

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

        widget.on_duration_changed(2000)
        widget.on_position_changed(1000)

        position_time = QTime(0, 0).addMSecs(1000).toString()
        duration_time = QTime(0, 0).addMSecs(2000).toString()

        assert widget.time_label.text() == f"{position_time} / {duration_time}"

    def test_should_toggle_play_button_icon(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

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
        assert widget.media_player.source().toLocalFile() == test_audio_path

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
