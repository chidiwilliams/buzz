from unittest.mock import patch

import numpy as np

from buzz.sounddevice_player import SounddevicePlayer


class FakeOutputStream:
    """Minimal stand-in for sd.OutputStream that records start/close calls."""

    instances = []

    def __init__(self, samplerate, channels, dtype, callback, finished_callback):
        self.samplerate = samplerate
        self.channels = channels
        self.callback = callback
        self.finished_callback = finished_callback
        self.latency = 0.25  # 250 ms output latency, typical of Windows defaults
        self.started = False
        self.closed = False
        FakeOutputStream.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True


def make_player(duration_s=10, samplerate=44100):
    data = np.zeros((duration_s * samplerate, 2), dtype=np.float32)
    return SounddevicePlayer(data, samplerate)


class TestPositionReporting:
    def test_position_compensates_for_output_latency(self):
        """Reported position is what is audible, not what has been buffered."""
        FakeOutputStream.instances = []
        with patch("buzz.sounddevice_player.sd.OutputStream", FakeOutputStream):
            player = make_player()
            player.play()

            # Callback has filled 2s of audio, but 250ms of it is still queued
            # in the device buffer and not yet audible.
            player._frame_pos = 2 * player.samplerate

            assert player.position_ms == 1750

    def test_position_never_negative_at_start(self):
        FakeOutputStream.instances = []
        with patch("buzz.sounddevice_player.sd.OutputStream", FakeOutputStream):
            player = make_player()
            player.play()
            player._frame_pos = 100  # less than one latency period

            assert player.position_ms == 0

    def test_position_without_stream_has_no_compensation(self):
        player = make_player()
        player._frame_pos = 2 * player.samplerate

        assert player.position_ms == 2000


class TestSeek:
    def test_seek_while_playing_does_not_reopen_the_device(self):
        """A seek mid-playback must not tear down and reopen the stream."""
        FakeOutputStream.instances = []
        with patch("buzz.sounddevice_player.sd.OutputStream", FakeOutputStream):
            player = make_player()
            player.play()
            assert len(FakeOutputStream.instances) == 1
            stream = FakeOutputStream.instances[0]

            for target_ms in (1000, 2000, 3000):
                player.seek(target_ms)

            assert len(FakeOutputStream.instances) == 1, (
                "seek reopened the output device, which drops audio"
            )
            assert not stream.closed
            assert stream.started
            assert player.is_playing

    def test_seek_while_playing_moves_the_read_cursor(self):
        FakeOutputStream.instances = []
        with patch("buzz.sounddevice_player.sd.OutputStream", FakeOutputStream):
            player = make_player()
            player.play()
            player.seek(3000)

            assert player._frame_pos == 3 * player.samplerate

    def test_seek_while_paused_sets_position_without_playing(self):
        FakeOutputStream.instances = []
        with patch("buzz.sounddevice_player.sd.OutputStream", FakeOutputStream):
            player = make_player()
            player.seek(4000)

            assert player._frame_pos == 4 * player.samplerate
            assert not player.is_playing
            assert FakeOutputStream.instances == []

    def test_seek_clamps_to_bounds(self):
        FakeOutputStream.instances = []
        with patch("buzz.sounddevice_player.sd.OutputStream", FakeOutputStream):
            player = make_player(duration_s=10)

            player.seek(-5000)
            assert player._frame_pos == 0

            player.seek(999_000)
            assert player._frame_pos == len(player.data)
