from unittest.mock import patch

import numpy as np
import pytest

from buzz import audio_devices
from buzz.sounddevice_player import SounddevicePlayer


@pytest.fixture(autouse=True)
def clean_stream_registry():
    """Streams left registered by another test would block device refreshes here."""
    audio_devices._active_streams.clear()
    yield
    audio_devices._active_streams.clear()


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


class TestDeviceRefresh:
    def test_play_refreshes_the_device_list(self):
        """Playback picks up devices connected since the last time we played."""
        FakeOutputStream.instances = []
        with patch("buzz.sounddevice_player.sd.OutputStream", FakeOutputStream), \
             patch("buzz.sounddevice_player.refresh_audio_devices") as mock_refresh:
            player = make_player()
            player.play()

            mock_refresh.assert_called_once()

    def test_play_retries_once_when_the_device_fails_to_start(self):
        """A device that vanishes between open and start is retried on the new default."""
        FakeOutputStream.instances = []

        class FailingOnceStream(FakeOutputStream):
            fail_next = True

            def start(self):
                if FailingOnceStream.fail_next:
                    FailingOnceStream.fail_next = False
                    raise RuntimeError("device unavailable")
                super().start()

        with patch("buzz.sounddevice_player.sd.OutputStream", FailingOnceStream), \
             patch("buzz.sounddevice_player.refresh_audio_devices") as mock_refresh:
            player = make_player()
            player.play()

            assert player.is_playing
            assert len(FakeOutputStream.instances) == 2
            assert FakeOutputStream.instances[1].started
            assert mock_refresh.call_count == 2

    def test_streams_are_registered_while_open(self):
        """PortAudio must not be restarted while a stream of ours is alive."""
        FakeOutputStream.instances = []
        with patch("buzz.sounddevice_player.sd.OutputStream", FakeOutputStream):
            player = make_player()
            player.play()
            stream = FakeOutputStream.instances[-1]

            assert stream in audio_devices._active_streams

            player.stop()

            assert stream not in audio_devices._active_streams


class TestRefreshAudioDevices:
    def test_refresh_restarts_portaudio(self):
        with patch("buzz.audio_devices.sd._terminate") as mock_terminate, \
             patch("buzz.audio_devices.sd._initialize") as mock_initialize:
            assert audio_devices.refresh_audio_devices() is True

            mock_terminate.assert_called_once()
            mock_initialize.assert_called_once()

    def test_refresh_is_skipped_while_a_stream_is_open(self):
        stream = FakeOutputStream(44100, 2, "float32", None, None)
        audio_devices.register_stream(stream)
        try:
            with patch("buzz.audio_devices.sd._terminate") as mock_terminate:
                assert audio_devices.refresh_audio_devices() is False

                mock_terminate.assert_not_called()
        finally:
            audio_devices.unregister_stream(stream)

    def test_refresh_survives_a_portaudio_error(self):
        with patch("buzz.audio_devices.sd._terminate", side_effect=OSError("boom")):
            assert audio_devices.refresh_audio_devices() is False
