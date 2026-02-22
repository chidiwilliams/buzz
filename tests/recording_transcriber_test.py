import threading
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest
from sounddevice import PortAudioError

from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.settings.recording_transcriber_mode import RecordingTranscriberMode
from buzz.transcriber.recording_transcriber import RecordingTranscriber
from buzz.transcriber.transcriber import TranscriptionOptions, Task


def make_transcriber(
    model_type=ModelType.WHISPER,
    mode_index=0,
    silence_threshold=0.0,
    language=None,
) -> RecordingTranscriber:
    options = TranscriptionOptions(
        language=language,
        task=Task.TRANSCRIBE,
        model=TranscriptionModel(model_type=model_type, whisper_model_size=WhisperModelSize.TINY),
        silence_threshold=silence_threshold,
    )
    mock_sounddevice = MagicMock()

    with patch("buzz.transcriber.recording_transcriber.Settings") as MockSettings:
        instance = MockSettings.return_value
        instance.value.return_value = mode_index
        transcriber = RecordingTranscriber(
            transcription_options=options,
            input_device_index=None,
            sample_rate=16000,
            model_path="tiny",
            sounddevice=mock_sounddevice,
        )
    return transcriber


class TestRecordingTranscriberInit:
    def test_default_batch_size_is_5_seconds(self):
        t = make_transcriber(mode_index=0)
        assert t.n_batch_samples == 5 * t.sample_rate

    def test_append_and_correct_mode_batch_size_is_3_seconds(self):
        mode_index = list(RecordingTranscriberMode).index(RecordingTranscriberMode.APPEND_AND_CORRECT)
        t = make_transcriber(mode_index=mode_index)
        assert t.n_batch_samples == 3 * t.sample_rate

    def test_append_and_correct_mode_keep_sample_seconds(self):
        mode_index = list(RecordingTranscriberMode).index(RecordingTranscriberMode.APPEND_AND_CORRECT)
        t = make_transcriber(mode_index=mode_index)
        assert t.keep_sample_seconds == 1.5

    def test_default_keep_sample_seconds(self):
        t = make_transcriber(mode_index=0)
        assert t.keep_sample_seconds == 0.15

    def test_queue_starts_empty(self):
        t = make_transcriber()
        assert t.queue.size == 0 or t.queue.ndim == 0

    def test_max_queue_size_is_three_batches(self):
        t = make_transcriber()
        assert t.max_queue_size == 3 * t.n_batch_samples


class TestAmplitude:
    def test_silence_returns_zero(self):
        arr = np.zeros(100, dtype=np.float32)
        assert RecordingTranscriber.amplitude(arr) == 0.0

    def test_unit_signal_returns_one(self):
        arr = np.ones(100, dtype=np.float32)
        assert abs(RecordingTranscriber.amplitude(arr) - 1.0) < 1e-6

    def test_rms_calculation(self):
        arr = np.array([0.6, 0.8], dtype=np.float32)
        expected = float(np.sqrt(np.mean(arr ** 2)))
        assert abs(RecordingTranscriber.amplitude(arr) - expected) < 1e-6


class TestStreamCallback:
    def test_emits_amplitude_changed(self):
        t = make_transcriber()
        emitted = []
        t.amplitude_changed.connect(lambda v: emitted.append(v))

        chunk = np.array([[0.5], [0.5]], dtype=np.float32)
        t.stream_callback(chunk, 2, None, None)

        assert len(emitted) == 1

    def test_appends_to_queue_when_not_full(self):
        t = make_transcriber()
        initial_size = t.queue.size
        chunk = np.ones((100,), dtype=np.float32)
        t.stream_callback(chunk.reshape(-1, 1), 100, None, None)
        assert t.queue.size == initial_size + 100

    def test_drops_chunk_when_queue_full(self):
        t = make_transcriber()
        # Fill the queue to max capacity
        t.queue = np.ones(t.max_queue_size, dtype=np.float32)
        size_before = t.queue.size

        chunk = np.array([[0.5], [0.5]], dtype=np.float32)
        t.stream_callback(chunk, 2, None, None)

        assert t.queue.size == size_before  # chunk was dropped

    def test_thread_safety_with_concurrent_callbacks(self):
        t = make_transcriber()
        errors = []

        def callback():
            try:
                chunk = np.ones((10, 1), dtype=np.float32)
                t.stream_callback(chunk, 10, None, None)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=callback) for _ in range(20)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert errors == []


class TestGetDeviceSampleRate:
    def test_returns_whisper_sample_rate_when_supported(self):
        with patch("sounddevice.check_input_settings"):
            rate = RecordingTranscriber.get_device_sample_rate(None)
        assert rate == 16000

    def test_falls_back_to_device_default_sample_rate(self):
        with patch("sounddevice.check_input_settings", side_effect=PortAudioError()), \
             patch("sounddevice.query_devices", return_value={"default_samplerate": 44100.0}):
            rate = RecordingTranscriber.get_device_sample_rate(None)
        assert rate == 44100

    def test_falls_back_to_whisper_rate_when_query_returns_non_dict(self):
        with patch("sounddevice.check_input_settings", side_effect=PortAudioError()), \
             patch("sounddevice.query_devices", return_value=None):
            rate = RecordingTranscriber.get_device_sample_rate(None)
        assert rate == 16000


class TestStopRecording:
    def test_sets_is_running_false(self):
        t = make_transcriber()
        t.is_running = True
        t.stop_recording()
        assert t.is_running is False

    def test_terminates_running_process(self):
        t = make_transcriber()
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # process is running
        t.process = mock_process

        t.stop_recording()

        mock_process.terminate.assert_called_once()

    def test_kills_process_on_timeout(self):
        import subprocess
        t = make_transcriber()
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)
        t.process = mock_process

        t.stop_recording()

        mock_process.kill.assert_called_once()

    def test_skips_terminate_when_process_already_stopped(self):
        t = make_transcriber()
        mock_process = MagicMock()
        mock_process.poll.return_value = 0  # already exited
        t.process = mock_process

        t.stop_recording()

        mock_process.terminate.assert_not_called()


class TestStartWithSilence:
    """Tests for the main transcription loop with silence threshold."""

    def _run_with_mock_model(self, transcription_options, samples, expected_text):
        """Helper to run a single transcription cycle with a mocked whisper model."""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": expected_text}

        transcriber = make_transcriber(
            model_type=ModelType.WHISPER,
            silence_threshold=0.0,
        )
        transcriber.transcription_options = transcription_options

        received = []
        transcriber.transcription.connect(lambda t: received.append(t))

        def fake_input_stream(**kwargs):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        transcriber.queue = samples.copy()
        transcriber.is_running = True

        # After processing one batch, stop.
        call_count = [0]
        original_emit = transcriber.transcription.emit

        def stop_after_first(text):
            original_emit(text)
            transcriber.is_running = False

        transcriber.transcription.emit = stop_after_first

        with patch("buzz.transcriber.recording_transcriber.whisper") as mock_whisper, \
             patch("buzz.transcriber.recording_transcriber.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            mock_whisper.load_model.return_value = mock_model
            mock_whisper.Whisper = type("Whisper", (), {})
            # make isinstance(model, whisper.Whisper) pass
            mock_model.__class__ = mock_whisper.Whisper

            with patch.object(transcriber, "sounddevice") as mock_sd:
                mock_stream_ctx = MagicMock()
                mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
                mock_stream_ctx.__exit__ = MagicMock(return_value=False)
                mock_sd.InputStream.return_value = mock_stream_ctx

                transcriber.start()

        return received

    def test_silent_audio_skips_transcription(self):
        t = make_transcriber(silence_threshold=1.0)  # very high threshold

        received = []
        t.transcription.connect(lambda text: received.append(text))

        # Put silent samples in queue (amplitude = 0)
        t.queue = np.zeros(t.n_batch_samples + 100, dtype=np.float32)
        t.is_running = True

        stop_event = threading.Event()

        def stop_after_delay():
            stop_event.wait(timeout=1.5)
            t.stop_recording()

        stopper = threading.Thread(target=stop_after_delay, daemon=True)

        with patch("buzz.transcriber.recording_transcriber.whisper") as mock_whisper, \
             patch("buzz.transcriber.recording_transcriber.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            mock_whisper.load_model.return_value = MagicMock()

            with patch.object(t, "sounddevice") as mock_sd:
                mock_stream_ctx = MagicMock()
                mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
                mock_stream_ctx.__exit__ = MagicMock(return_value=False)
                mock_sd.InputStream.return_value = mock_stream_ctx

                stopper.start()
                stop_event.set()
                t.start()

        # No transcription should have been emitted since audio is silent
        assert received == []


class TestStartPortAudioError:
    def test_emits_error_on_portaudio_failure(self):
        t = make_transcriber()
        errors = []
        t.error.connect(lambda e: errors.append(e))

        with patch("buzz.transcriber.recording_transcriber.whisper") as mock_whisper, \
             patch("buzz.transcriber.recording_transcriber.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            mock_whisper.load_model.return_value = MagicMock()

            with patch.object(t, "sounddevice") as mock_sd:
                mock_sd.InputStream.side_effect = PortAudioError()
                t.start()

        assert len(errors) == 1
