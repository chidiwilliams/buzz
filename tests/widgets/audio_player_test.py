
import os

from PyQt6.QtCore import QTime
from PyQt6.QtMultimedia import QMediaPlayer
from pytestqt.qtbot import QtBot

from buzz.widgets.audio_player import AudioPlayer
from tests.audio import test_audio_path


class TestAudioPlayer:
    def test_should_load_audio(self, qtbot: QtBot):
        widget = AudioPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert widget.media_player.source().toLocalFile() == test_audio_path

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
