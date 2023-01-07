from unittest.mock import Mock, patch

from buzz.recording import RecordingAmplitudeListener
from tests.mock_sounddevice import MockInputStream


class TestRecordingAmplitudeListener:
    def test_should_emit_amplitude_changed(self, qtbot):
        listener = RecordingAmplitudeListener()

        mock_amplitude_changed = Mock()
        listener.amplitude_changed.connect(mock_amplitude_changed)

        with qtbot.wait_signal(listener.amplitude_changed, timeout=60 * 1000), patch('sounddevice.InputStream',
                                                                                     side_effect=MockInputStream):
            listener.start_recording()

        listener.stop_recording()
        mock_amplitude_changed.assert_called_with(0.06511624157428741)
