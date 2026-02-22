import struct
import subprocess
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

from buzz.audio_source import (
    AudioSourceConfig,
    ScreenCaptureAudioSource,
    SoundDeviceAudioSource,
    get_screen_audio_helper_path,
)


class TestAudioSourceConfig:
    def test_sounddevice_config(self):
        config = AudioSourceConfig(source_type="sounddevice", device_index=3)
        assert config.source_type == "sounddevice"
        assert config.device_index == 3
        assert config.helper_path is None

    def test_screen_capture_config(self):
        config = AudioSourceConfig(
            source_type="screen_capture",
            helper_path="/usr/local/bin/buzz-screen-audio",
        )
        assert config.source_type == "screen_capture"
        assert config.helper_path == "/usr/local/bin/buzz-screen-audio"
        assert config.device_index is None


class TestSoundDeviceAudioSource:
    def test_delegates_to_sounddevice_input_stream(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream
        callback = MagicMock()

        source = SoundDeviceAudioSource(
            sounddevice_module=mock_sd,
            samplerate=16000,
            device=3,
            dtype="float32",
            channels=1,
            callback=callback,
        )

        mock_sd.InputStream.assert_called_once_with(
            samplerate=16000,
            device=3,
            dtype="float32",
            channels=1,
            callback=callback,
        )

    def test_context_manager_delegates(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream
        callback = MagicMock()

        source = SoundDeviceAudioSource(
            sounddevice_module=mock_sd,
            samplerate=16000,
            device=3,
            dtype="float32",
            channels=1,
            callback=callback,
        )

        with source:
            mock_stream.__enter__.assert_called_once()

        mock_stream.__exit__.assert_called_once()


class TestScreenCaptureAudioSource:
    def _make_pcm_data(self, num_samples: int) -> bytes:
        """Create raw float32 PCM bytes."""
        samples = np.random.uniform(-1.0, 1.0, num_samples).astype(np.float32)
        return samples.tobytes()

    @patch("buzz.audio_source.subprocess.Popen")
    def test_spawns_helper_and_reads_audio(self, mock_popen):
        sample_rate = 16000
        chunk_samples = sample_rate // 10  # 1600 samples per chunk
        num_chunks = 3

        # Prepare canned PCM data: enough for num_chunks reads then EOF
        pcm_data = self._make_pcm_data(chunk_samples * num_chunks)

        mock_process = MagicMock()
        mock_process.poll.return_value = None

        # Mock stdout.read to return chunks then empty bytes (EOF)
        read_calls = []
        offset = 0
        chunk_bytes = chunk_samples * 4
        while offset < len(pcm_data):
            read_calls.append(pcm_data[offset : offset + chunk_bytes])
            offset += chunk_bytes
        read_calls.append(b"")  # EOF

        mock_process.stdout.read = MagicMock(side_effect=read_calls)
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        received_chunks = []
        callback = MagicMock(side_effect=lambda in_data, *args: received_chunks.append(in_data.copy()))

        source = ScreenCaptureAudioSource(
            helper_path="/fake/buzz-screen-audio",
            sample_rate=sample_rate,
            callback=callback,
        )

        with source:
            # Wait for reader thread to process all chunks
            time.sleep(0.5)

        assert len(received_chunks) == num_chunks
        for chunk in received_chunks:
            assert chunk.dtype == np.float32
            assert chunk.shape == (chunk_samples, 1)

    @patch("buzz.audio_source.subprocess.Popen")
    def test_terminates_process_on_exit(self, mock_popen):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        # stdout.read blocks until stop
        mock_process.stdout.read = MagicMock(side_effect=lambda _: b"")
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        source = ScreenCaptureAudioSource(
            helper_path="/fake/buzz-screen-audio",
            sample_rate=16000,
            callback=MagicMock(),
        )

        with source:
            pass

        mock_process.terminate.assert_called_once()

    @patch("buzz.audio_source.subprocess.Popen")
    def test_passes_sample_rate_arg(self, mock_popen):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.read = MagicMock(return_value=b"")
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        source = ScreenCaptureAudioSource(
            helper_path="/fake/buzz-screen-audio",
            sample_rate=16000,
            callback=MagicMock(),
        )

        with source:
            pass

        mock_popen.assert_called_once_with(
            ["/fake/buzz-screen-audio", "--sample-rate", "16000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

    @patch("buzz.audio_source.subprocess.Popen")
    def test_handles_partial_chunk(self, mock_popen):
        """Verify partial reads are zero-padded to full chunk size."""
        sample_rate = 16000
        chunk_samples = sample_rate // 10  # 1600
        chunk_bytes = chunk_samples * 4

        # Send a partial chunk (half a chunk) then EOF
        partial_data = self._make_pcm_data(chunk_samples // 2)
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.read = MagicMock(side_effect=[partial_data, b""])
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        received = []
        callback = MagicMock(side_effect=lambda in_data, *args: received.append(in_data.copy()))

        source = ScreenCaptureAudioSource(
            helper_path="/fake/buzz-screen-audio",
            sample_rate=sample_rate,
            callback=callback,
        )

        with source:
            time.sleep(0.3)

        # Should get one padded chunk
        assert len(received) == 1
        assert received[0].shape == (chunk_samples, 1)


class TestGetScreenAudioHelperPath:
    @patch("buzz.audio_source.os.path.isfile")
    @patch("buzz.audio_source.APP_BASE_DIR", "/app")
    def test_finds_primary_path(self, mock_isfile):
        mock_isfile.side_effect = lambda p: p == "/app/whisper_cpp/buzz-screen-audio"
        assert get_screen_audio_helper_path() == "/app/whisper_cpp/buzz-screen-audio"

    @patch("buzz.audio_source.os.path.isfile")
    @patch("buzz.audio_source.APP_BASE_DIR", "/app")
    def test_finds_fallback_path(self, mock_isfile):
        mock_isfile.side_effect = lambda p: p == "/app/buzz/whisper_cpp/buzz-screen-audio"
        assert get_screen_audio_helper_path() == "/app/buzz/whisper_cpp/buzz-screen-audio"

    @patch("buzz.audio_source.os.path.isfile", return_value=False)
    @patch("buzz.audio_source.APP_BASE_DIR", "/app")
    def test_returns_none_when_not_found(self, mock_isfile):
        assert get_screen_audio_helper_path() is None
