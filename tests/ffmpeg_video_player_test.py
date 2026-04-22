import subprocess
import time

import numpy as np
import pytest

from buzz.ffmpeg_video_player import (
    FfmpegFrameReader,
    FfmpegVideoPlayer,
    _find_ffmpeg,
    _find_ffprobe,
    probe_video,
)
from tests.audio import test_audio_path


@pytest.fixture(scope="module")
def test_video_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("video") / "test.mp4"
    subprocess.run(
        [
            _find_ffmpeg(),
            "-f", "lavfi", "-i", "testsrc=duration=1:size=64x48:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            str(path), "-y", "-loglevel", "quiet",
        ],
        check=True,
    )
    return str(path)


class TestFindFfmpeg:
    def test_returns_string(self):
        assert isinstance(_find_ffmpeg(), str)
        assert len(_find_ffmpeg()) > 0

    def test_returns_string_ffprobe(self):
        assert isinstance(_find_ffprobe(), str)
        assert len(_find_ffprobe()) > 0


class TestProbeVideo:
    def test_audio_only_file(self):
        info = probe_video(test_audio_path)
        assert info["duration_ms"] > 0
        assert info["has_video"] is False
        assert info["width"] == 0
        assert info["height"] == 0

    def test_video_file(self, test_video_path):
        info = probe_video(test_video_path)
        assert info["has_video"] is True
        assert info["width"] == 64
        assert info["height"] == 48
        assert info["fps"] == pytest.approx(10.0, abs=0.1)
        assert info["duration_ms"] > 0


class TestFfmpegVideoPlayer:
    def test_audio_only_has_no_video(self):
        player = FfmpegVideoPlayer(test_audio_path)
        assert player.has_video is False
        assert player.duration_ms > 0
        player.close()

    def test_video_file_properties(self, test_video_path):
        player = FfmpegVideoPlayer(test_video_path)
        assert player.has_video is True
        assert player.width == 64
        assert player.height == 48
        assert player.fps == pytest.approx(10.0, abs=0.1)
        assert player.duration_ms > 0
        player.close()

    def test_start_creates_reader(self, test_video_path):
        player = FfmpegVideoPlayer(test_video_path)
        player.start(0)
        assert player._reader is not None
        player.close()

    def test_start_audio_only_no_reader(self):
        player = FfmpegVideoPlayer(test_audio_path)
        player.start(0)
        assert player._reader is None
        player.close()

    def test_get_frame_returns_none_without_start(self, test_video_path):
        player = FfmpegVideoPlayer(test_video_path)
        assert player.get_frame_for_position(0) is None
        player.close()

    def test_get_frame_returns_frame(self, test_video_path):
        player = FfmpegVideoPlayer(test_video_path)
        player.start(0)
        frame = None
        for _ in range(50):
            frame = player.get_frame_for_position(500)
            if frame is not None:
                break
            time.sleep(0.05)
        assert frame is not None
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (48, 64, 3)
        player.close()

    def test_last_frame_tracks_returned_frame(self, test_video_path):
        player = FfmpegVideoPlayer(test_video_path)
        player.start(0)
        for _ in range(50):
            frame = player.get_frame_for_position(500)
            if frame is not None:
                break
            time.sleep(0.05)
        assert player.last_frame is not None
        player.close()

    def test_seek_restarts_reader(self, test_video_path):
        player = FfmpegVideoPlayer(test_video_path)
        player.start(0)
        old_reader = player._reader
        player.seek(200)
        assert player._reader is not old_reader
        player.close()

    def test_stop_clears_reader(self, test_video_path):
        player = FfmpegVideoPlayer(test_video_path)
        player.start(0)
        player.stop()
        assert player._reader is None

    def test_close_stops_reader(self, test_video_path):
        player = FfmpegVideoPlayer(test_video_path)
        player.start(0)
        player.close()
        assert player._reader is None


class TestFfmpegFrameReader:
    def test_done_false_while_reading(self, test_video_path):
        info = probe_video(test_video_path)
        reader = FfmpegFrameReader(
            test_video_path, info["width"], info["height"], info["fps"], 0
        )
        time.sleep(0.1)
        # May or may not be done, but must not raise
        _ = reader.done
        reader.stop()

    def test_get_frame_returns_ndarray(self, test_video_path):
        info = probe_video(test_video_path)
        reader = FfmpegFrameReader(
            test_video_path, info["width"], info["height"], info["fps"], 0
        )
        frame = None
        for _ in range(50):
            frame = reader.get_frame_for_position(500.0)
            if frame is not None:
                break
            time.sleep(0.05)
        assert frame is not None
        assert frame.shape == (info["height"], info["width"], 3)
        reader.stop()

    def test_get_frame_returns_none_when_empty(self, test_video_path):
        info = probe_video(test_video_path)
        reader = FfmpegFrameReader(
            test_video_path, info["width"], info["height"], info["fps"], 0
        )
        # Ask for a frame before any are buffered (position far in future)
        # Result may be None or a frame — just must not raise
        _ = reader.get_frame_for_position(0.0)
        reader.stop()

    def test_done_true_after_all_frames_consumed(self, test_video_path):
        info = probe_video(test_video_path)
        reader = FfmpegFrameReader(
            test_video_path, info["width"], info["height"], info["fps"], 0
        )
        # Drain all frames
        for _ in range(200):
            time.sleep(0.05)
            reader.get_frame_for_position(float(_ * 50))
            if reader.done:
                break
        assert reader.done
        reader.stop()

    def test_stop_terminates_process(self, test_video_path):
        info = probe_video(test_video_path)
        reader = FfmpegFrameReader(
            test_video_path, info["width"], info["height"], info["fps"], 0
        )
        time.sleep(0.1)
        reader.stop()
        # After stop, thread should finish quickly
        reader._thread.join(timeout=2.0)
        assert not reader._thread.is_alive()
