import io
import os
import subprocess
import sys
import threading
from unittest.mock import patch

import numpy as np
import pytest

from buzz import audio_devices
from buzz.sounddevice_player import (
    AudioDecoder, AudioFilePlayer, SounddevicePlayer, MIN_BUFFER_BYTES, _read_samples,
    FRAME_BYTES, SAMPLE_RATE,
)
from buzz.ffmpeg_utils import find_ffmpeg
from tests.audio import test_audio_path


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
        self.dtype = dtype
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


class TestAudioDecoder:
    def test_decodes_to_16_bit_stereo(self):
        data = AudioDecoder(test_audio_path).decode()

        assert data.dtype == np.int16
        assert data.shape[1] == 2
        assert len(data) > 44100  # more than a second of audio

    def test_cancelled_decoder_returns_nothing(self):
        decoder = AudioDecoder(test_audio_path)
        decoder.cancel()

        assert decoder.decode() is None

    def test_file_player_is_not_ready_when_cancelled(self):
        decoder = AudioDecoder(test_audio_path)
        decoder.cancel()

        assert not AudioFilePlayer(test_audio_path, decoder=decoder).ready

    def test_reports_ffmpeg_errors(self, tmp_path):
        not_audio = tmp_path / "notes.mp3"
        not_audio.write_text("not audio")

        with pytest.raises(subprocess.CalledProcessError) as error:
            AudioDecoder(str(not_audio)).decode()
        assert error.value.stderr

    def test_buffer_is_trimmed_to_the_samples(self):
        """A buffer sized for far more audio than there is is not kept alive by the samples."""
        raw = bytes(MIN_BUFFER_BYTES)

        samples = _read_samples(io.BytesIO(raw), expected_bytes=20 * len(raw))

        base = samples
        while isinstance(base, np.ndarray) and base.base is not None:
            base = base.base
        assert memoryview(base).nbytes == len(raw)

    def test_expects_the_duration_of_the_audio_stream(self, tmp_path):
        """A long video with a short audio track is not sized by the video."""
        video = str(tmp_path / "video.mp4")
        subprocess.run(
            [find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "color=size=16x16:rate=1:duration=60",
             "-f", "lavfi", "-i", "sine=duration=2", "-c:v", "libx264", "-c:a", "aac", video],
            check=True)

        expected_s = AudioDecoder(video)._expected_bytes() / FRAME_BYTES / SAMPLE_RATE

        assert 1.9 < expected_s < 2.2

    @pytest.mark.skipif(sys.platform == "win32", reason="uses a named pipe")
    def test_cancel_stops_a_stalled_probe(self, tmp_path):
        # Opening a named pipe blocks until something writes to it
        stalled = str(tmp_path / "stalled.mp3")
        os.mkfifo(stalled)
        decoder = AudioDecoder(stalled)
        decoding = threading.Thread(target=decoder.decode)
        decoding.start()

        for _ in range(100):
            if decoder._process is not None:
                break
            threading.Event().wait(0.05)
        decoder.cancel()
        decoding.join(5)

        assert not decoding.is_alive()

    def test_reads_more_samples_than_expected(self):
        raw = (np.arange(MIN_BUFFER_BYTES * 3 // 2) % 30_000).astype(np.int16).tobytes()

        samples = _read_samples(io.BytesIO(raw + b"\x01"), expected_bytes=0)

        # The trailing partial frame is dropped
        assert samples.tobytes() == raw
        assert samples.shape[1] == 2

    def test_reports_decoding_progress(self):
        progress = []

        AudioDecoder(test_audio_path, on_progress=progress.append).decode()

        assert progress
        assert progress == sorted(progress)
        assert progress[-1] > 0.9

    def test_reading_reports_fraction_of_expected_bytes(self):
        raw = bytes(MIN_BUFFER_BYTES)
        progress = []

        _read_samples(io.BytesIO(raw), expected_bytes=2 * len(raw), on_progress=progress.append)

        assert progress == [0.5]

    def test_file_player_shares_samples(self):
        data = np.zeros((44100, 2), dtype=np.int16)

        player = AudioFilePlayer("unused.mp3", samples=data)

        assert player.ready
        assert player.samples is data

    def test_stream_plays_samples_in_their_own_format(self):
        """int16 samples are played as they are, without a float32 copy."""
        FakeOutputStream.instances = []
        with patch("buzz.sounddevice_player.sd.OutputStream", FakeOutputStream):
            data = np.zeros((44100, 2), dtype=np.int16)
            player = SounddevicePlayer(data, 44100)
            player.play()

            assert FakeOutputStream.instances[-1].dtype == "int16"

            outdata = np.ones((512, 2), dtype=np.int16)
            player._callback(outdata, 512, None, None)
            assert not outdata.any()

            player.stop()


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
