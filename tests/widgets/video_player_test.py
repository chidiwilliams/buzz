import os

import numpy as np
import pytest
from PyQt6.QtCore import QTime
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QVBoxLayout, QLabel
from pytestqt.qtbot import QtBot

from buzz.widgets.video_player import VideoPlayer
from tests.audio import test_audio_path


def assert_approximately_equal(actual, expected, tolerance=0.001):
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
        assert widget.video_label is not None
        assert widget.media_player is not None
        assert os.path.normpath(widget.media_player.source().toLocalFile()) == os.path.normpath(test_audio_path)

    def test_video_label_is_a_qlabel(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert isinstance(widget.video_label, QLabel)

    def test_video_label_has_size_constraints(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert widget.video_label.minimumHeight() == 200
        assert widget.video_label.maximumHeight() == 400

    def test_video_label_has_black_background(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert "black" in widget.video_label.styleSheet()

    def test_qt_audio_is_muted(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Qt audio output must always be muted — sounddevice handles audio
        assert widget.audio_output.isMuted()

    def test_qt_media_player_has_no_video_output(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # We render frames ourselves via ffmpeg, so Qt must not have a video sink
        assert widget.media_player.videoOutput() is None

    def test_has_ffmpeg_video_player(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert widget._ffmpeg_player is not None

    def test_render_timer_is_running(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert widget._render_timer.isActive()

    def test_display_frame_sets_pixmap(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)
        widget.show()
        qtbot.waitExposed(widget)

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        frame[:, :100] = [255, 0, 0]  # red left half
        widget._display_frame(frame)

        assert not widget.video_label.pixmap().isNull()

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

        layout = widget.layout()
        assert isinstance(layout, QVBoxLayout)
        # video_label + controls layout
        assert layout.count() == 2

    def test_should_handle_range_looping(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.set_range((1000, 3000))
        assert widget.range_ms == (1000, 3000)

        widget.clear_range()
        assert widget.range_ms is None

    def test_should_stop_playback(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.stop()
        assert widget.media_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState

    def test_render_timer_stops_on_stop(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.stop()
        assert not widget._render_timer.isActive()

    def test_should_set_position(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.set_position(1000)

    def test_set_position_seeks_ffmpeg_player(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # After seek, the ffmpeg reader should restart (reader will be non-None if has_video)
        widget.set_position(500)
        # No assertion on internal state — just verify no exception is raised

    def test_should_track_slider_dragging(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert widget.is_slider_dragging is False

        widget.on_slider_pressed()
        assert widget.is_slider_dragging is True

        widget.on_slider_released()
        assert widget.is_slider_dragging is False

    def test_should_emit_position_changed_signal(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

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

        assert hasattr(widget, 'toggle_playback')

    def test_should_have_audio_output(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert widget.audio_output is not None
        assert widget.media_player.audioOutput() == widget.audio_output

    def test_should_handle_range_with_position_outside(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.position_ms = 5000
        widget.set_range((1000, 3000))
        assert widget.range_ms == (1000, 3000)

    def test_should_handle_range_with_position_inside(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.position_ms = 2000
        widget.set_range((1000, 3000))
        assert widget.range_ms == (1000, 3000)

    def test_should_loop_at_range_end(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.set_range((1000, 3000))
        widget.is_looping = False
        widget.on_position_changed(2960)

        assert widget.is_looping is False

    def test_should_not_update_scrubber_while_dragging(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.on_duration_changed(5000)
        widget.scrubber.setValue(1000)
        widget.on_slider_pressed()
        widget.on_position_changed(2000)

        assert widget.scrubber.value() == 1000

        widget.on_slider_released()

    def test_should_update_scrubber_when_not_dragging(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        widget.on_duration_changed(5000)
        widget.is_slider_dragging = False
        widget.on_position_changed(2000)

        assert widget.scrubber.value() == 2000

    def test_on_media_status_changed_is_no_op(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        # Duration comes from ffprobe, so media status changes are no-ops
        widget.on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)
        widget.on_media_status_changed(QMediaPlayer.MediaStatus.BufferedMedia)
        # No state change expected — just must not raise

    def test_play_button_sizing(self, qtbot: QtBot):
        widget = VideoPlayer(test_audio_path)
        qtbot.add_widget(widget)

        assert widget.play_button.maximumWidth() == 40
        assert widget.play_button.minimumHeight() == 30
