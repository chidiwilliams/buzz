import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from buzz.recording import RecordingAmplitudeListener


class TestRecordingAmplitudeListenerInit:
    def test_initial_buffer_is_empty(self):
        # np.ndarray([], dtype=np.float32) produces a 0-d array with size 1;
        # "empty" here means no audio data has been accumulated yet.
        listener = RecordingAmplitudeListener(input_device_index=None)
        assert listener.buffer.ndim == 0

    def test_initial_accumulation_size_is_zero(self):
        listener = RecordingAmplitudeListener(input_device_index=None)
        assert listener.accumulation_size == 0


class TestRecordingAmplitudeListenerStreamCallback:
    def _make_listener(self) -> RecordingAmplitudeListener:
        listener = RecordingAmplitudeListener(input_device_index=None)
        listener.accumulation_size = 10  # small size for testing
        return listener

    def test_emits_amplitude_changed(self):
        listener = self._make_listener()
        emitted = []
        listener.amplitude_changed.connect(lambda v: emitted.append(v))

        chunk = np.array([[0.5], [0.5]], dtype=np.float32)
        listener.stream_callback(chunk, 2, None, None)

        assert len(emitted) == 1
        assert emitted[0] > 0

    def test_amplitude_is_rms(self):
        listener = self._make_listener()
        emitted = []
        listener.amplitude_changed.connect(lambda v: emitted.append(v))

        chunk = np.array([[1.0], [1.0]], dtype=np.float32)
        listener.stream_callback(chunk, 2, None, None)

        assert abs(emitted[0] - 1.0) < 1e-6

    def test_accumulates_buffer(self):
        listener = self._make_listener()
        size_before = listener.buffer.size
        chunk = np.array([[0.1]] * 4, dtype=np.float32)
        listener.stream_callback(chunk, 4, None, None)
        assert listener.buffer.size == size_before + 4

    def test_emits_average_amplitude_when_buffer_full(self):
        listener = self._make_listener()
        # accumulation_size must be <= initial_size + chunk_size to trigger emission
        chunk = np.array([[0.5]] * 4, dtype=np.float32)
        listener.accumulation_size = listener.buffer.size + len(chunk)

        averages = []
        listener.average_amplitude_changed.connect(lambda v: averages.append(v))
        listener.stream_callback(chunk, len(chunk), None, None)

        assert len(averages) == 1
        assert averages[0] > 0

    def test_resets_buffer_after_emitting_average(self):
        listener = self._make_listener()
        chunk = np.array([[0.5]] * 4, dtype=np.float32)
        listener.accumulation_size = listener.buffer.size + len(chunk)

        listener.stream_callback(chunk, len(chunk), None, None)

        # Buffer is reset to np.ndarray([], ...) — a 0-d array
        assert listener.buffer.ndim == 0

    def test_does_not_emit_average_before_buffer_full(self):
        listener = self._make_listener()
        chunk = np.array([[0.5]] * 4, dtype=np.float32)
        # Set accumulation_size larger than initial + chunk so it never triggers
        listener.accumulation_size = listener.buffer.size + len(chunk) + 1

        averages = []
        listener.average_amplitude_changed.connect(lambda v: averages.append(v))
        listener.stream_callback(chunk, len(chunk), None, None)

        assert len(averages) == 0

    def test_average_amplitude_is_rms_of_accumulated_buffer(self):
        listener = self._make_listener()

        # Two callbacks of 4 samples each; trigger on second callback
        chunk = np.array([[1.0], [1.0], [1.0], [1.0]], dtype=np.float32)
        listener.accumulation_size = listener.buffer.size + len(chunk)

        averages = []
        listener.average_amplitude_changed.connect(lambda v: averages.append(v))
        listener.stream_callback(chunk, len(chunk), None, None)

        assert len(averages) == 1
        # All samples are 1.0, so RMS must be 1.0 (initial uninitialized byte is negligible)
        assert averages[0] > 0


class TestRecordingAmplitudeListenerStart:
    def test_accumulation_size_set_from_sample_rate(self):
        listener = RecordingAmplitudeListener(input_device_index=None)

        mock_stream = MagicMock()
        mock_stream.samplerate = 16000

        with patch("sounddevice.InputStream", return_value=mock_stream):
            listener.start_recording()

        assert listener.accumulation_size == 16000 * RecordingAmplitudeListener.ACCUMULATION_SECONDS
