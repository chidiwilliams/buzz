
import os
import pytest

from PyQt6.QtCore import QTime
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QHBoxLayout
from pytestqt.qtbot import QtBot

from buzz.widgets.audio_player import AudioPlayer
from tests.audio import test_audio_path


def assert_speed_approximately_equal(actual, expected, tolerance=0.001):
    """Helper function to compare speeds with tolerance for floating-point precision"""
    assert abs(actual - expected) < tolerance, f"Speed {actual} is not approximately equal to {expected}"


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

    def test_should_have_smart_speed_control(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Check basic speed control elements
        assert widget.speed_label.text() == "Speed:"
        assert widget.speed_combo.count() == 6
        # The combo box will load the saved rate from settings, so we just check it's a valid format
        current_text = widget.speed_combo.currentText()
        assert current_text.endswith('x')
        assert widget.speed_combo.isEditable() == True
        
        # Check increment buttons
        assert widget.speed_down_btn.text() == "-"
        assert widget.speed_up_btn.text() == "+"
        assert widget.speed_down_btn.maximumWidth() == 25
        assert widget.speed_up_btn.maximumWidth() == 25

    def test_should_change_playback_speed_via_preset(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test setting speed via preset dropdown
        widget.on_speed_changed("1.5x")
        assert widget.speed_combo.currentText() == "1.5x"
        assert_speed_approximately_equal(widget.media_player.playbackRate(), 1.5)

    def test_should_change_playback_speed_via_custom_input(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test setting custom speed by typing
        widget.on_speed_changed("1.7")
        assert widget.speed_combo.currentText() == "1.70x"
        assert_speed_approximately_equal(widget.media_player.playbackRate(), 1.7)

    def test_should_increase_speed_with_button(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        initial_speed = widget.get_current_speed()
        widget.increase_speed()
        
        expected_speed = initial_speed + 0.05
        assert_speed_approximately_equal(widget.get_current_speed(), expected_speed)
        assert_speed_approximately_equal(widget.media_player.playbackRate(), expected_speed)

    def test_should_decrease_speed_with_button(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        initial_speed = widget.get_current_speed()
        widget.decrease_speed()
        
        expected_speed = initial_speed - 0.05
        assert_speed_approximately_equal(widget.get_current_speed(), expected_speed)
        assert_speed_approximately_equal(widget.media_player.playbackRate(), expected_speed)

    def test_should_respect_speed_limits(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test minimum speed limit
        widget.on_speed_changed("0.05")  # Below minimum
        assert widget.speed_combo.currentText() == "0.10x"
        assert_speed_approximately_equal(widget.media_player.playbackRate(), 0.1)

        # Test maximum speed limit
        widget.on_speed_changed("10.0")  # Above maximum
        assert widget.speed_combo.currentText() == "5.00x"
        assert_speed_approximately_equal(widget.media_player.playbackRate(), 5.0)

    def test_should_get_current_speed(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.speed_combo.setCurrentText("2.3x")
        assert widget.get_current_speed() == 2.3

    def test_should_reset_speed(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Set speed to something other than 1x
        widget.set_speed(1.5)
        assert_speed_approximately_equal(widget.media_player.playbackRate(), 1.5)

        # Reset speed
        widget.reset_speed()
        assert widget.speed_combo.currentText() == "1.00x"
        assert_speed_approximately_equal(widget.media_player.playbackRate(), 1.0)

    def test_should_handle_invalid_media_speed_control(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.set_invalid_media(True)
        assert widget.speed_combo.isEnabled() == False
        assert widget.speed_down_btn.isEnabled() == False
        assert widget.speed_up_btn.isEnabled() == False

        widget.set_invalid_media(False)
        assert widget.speed_combo.isEnabled() == True
        assert widget.speed_down_btn.isEnabled() == True
        assert widget.speed_up_btn.isEnabled() == True

    def test_should_handle_invalid_speed_input(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test invalid input
        initial_text = widget.speed_combo.currentText()
        widget.on_speed_changed("invalid")
        assert widget.speed_combo.currentText() == initial_text

    def test_should_format_speed_text_correctly(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Test that custom input gets formatted with "x" suffix
        widget.on_speed_changed("1.75")
        assert widget.speed_combo.currentText() == "1.75x"
        
        # Test that preset values keep their format
        widget.on_speed_changed("2x")
        assert widget.speed_combo.currentText() == "2x"

    def test_should_use_single_row_layout(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Check that we have a single row layout
        layout = widget.layout()
        assert isinstance(layout, QHBoxLayout)
        assert layout.count() == 7  # speed_label, speed_combo, speed_down_btn, speed_up_btn, play_button, scrubber, time_label

    def test_should_persist_playback_rate_setting(self, qtbot: QtBot):
        """Test that playback rate is saved to and loaded from settings"""
        # Create first audio player - should load default or saved rate
        widget1 = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget1)
        
        # Change speed to something other than default
        widget1.set_speed(1.75)
        assert_speed_approximately_equal(widget1.get_current_speed(), 1.75)
        
        # Create second audio player - should load the saved rate
        widget2 = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget2)
        
        # Should have the same speed as the first player
        assert_speed_approximately_equal(widget2.get_current_speed(), 1.75)
        assert_speed_approximately_equal(widget2.media_player.playbackRate(), 1.75)
