import os
import sys
import time
import numpy as np
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtCore import QThread

from buzz.locale import _
from buzz.assets import APP_BASE_DIR
from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.recording_transcriber import RecordingTranscriber
from buzz.transcriber.transcriber import TranscriptionOptions, Task
from buzz.settings.recording_transcriber_mode import RecordingTranscriberMode
from tests.mock_sounddevice import MockSoundDevice
from tests.model_loader import get_model_path


class TestAmplitude:
    def test_symmetric_array(self):
        arr = np.array([1.0, -1.0, 2.0, -2.0])
        amplitude = RecordingTranscriber.amplitude(arr)
        assert amplitude == 2.0

    def test_asymmetric_array(self):
        arr = np.array([1.0, 2.0, 3.0, -1.0])
        amplitude = RecordingTranscriber.amplitude(arr)
        # (abs(3.0) + abs(-1.0)) / 2 = (3.0 + 1.0) / 2 = 2.0
        assert amplitude == 2.0

    def test_all_zeros(self):
        arr = np.array([0.0, 0.0, 0.0])
        amplitude = RecordingTranscriber.amplitude(arr)
        assert amplitude == 0.0

    def test_all_positive(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0])
        amplitude = RecordingTranscriber.amplitude(arr)
        # (abs(4.0) + abs(1.0)) / 2 = (4.0 + 1.0) / 2 = 2.5
        assert amplitude == 2.5

    def test_all_negative(self):
        arr = np.array([-1.0, -2.0, -3.0, -4.0])
        amplitude = RecordingTranscriber.amplitude(arr)
        # (abs(-1.0) + abs(-4.0)) / 2 = (1.0 + 4.0) / 2 = 2.5
        assert amplitude == 2.5


class TestGetDeviceSampleRate:
    def test_returns_default_16khz_when_supported(self):
        with patch("sounddevice.check_input_settings"):
            rate = RecordingTranscriber.get_device_sample_rate(None)
            assert rate == 16000

    def test_falls_back_to_device_default(self):
        import sounddevice
        from sounddevice import PortAudioError

        def raise_error(*args, **kwargs):
            raise PortAudioError("Device doesn't support 16000")

        device_info = {"default_samplerate": 44100}
        with patch("sounddevice.check_input_settings", side_effect=raise_error), \
             patch("sounddevice.query_devices", return_value=device_info):
            rate = RecordingTranscriber.get_device_sample_rate(0)
            assert rate == 44100

    def test_returns_default_when_query_fails(self):
        from sounddevice import PortAudioError

        def raise_error(*args, **kwargs):
            raise PortAudioError("Device doesn't support 16000")

        with patch("sounddevice.check_input_settings", side_effect=raise_error), \
             patch("sounddevice.query_devices", return_value=None):
            rate = RecordingTranscriber.get_device_sample_rate(0)
            assert rate == 16000


class TestRecordingTranscriber:

    def test_should_transcribe(self, qtbot):
        with (patch("sounddevice.check_input_settings")):
            thread = QThread()

            transcription_model = TranscriptionModel(
                model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY
            )

            model_path = get_model_path(transcription_model)

            model_exe_path = os.path.join(APP_BASE_DIR, "whisper_cpp", "whisper-server.exe")
            if sys.platform.startswith("win"):
                assert os.path.exists(model_exe_path), f"{model_exe_path} does not exist"

            transcriber = RecordingTranscriber(
                transcription_options=TranscriptionOptions(
                    model=transcription_model, language="fr", task=Task.TRANSCRIBE
                ),
                input_device_index=0,
                sample_rate=16_000,
                model_path=model_path,
                sounddevice=MockSoundDevice(),
            )
            transcriber.moveToThread(thread)

            thread.started.connect(transcriber.start)

            transcriptions = []

            def on_transcription(text):
                transcriptions.append(text)

            transcriber.transcription.connect(on_transcription)

            thread.start()
            qtbot.waitUntil(lambda: len(transcriptions) == 3, timeout=60_000)

            # any string in any transcription
            strings_to_check = [_("Starting Whisper.cpp..."), "Bienvenue dans Passe"]
            assert any(s in t for s in strings_to_check for t in transcriptions)

            # Wait for the thread to finish
            transcriber.stop_recording()
            time.sleep(10)

            thread.quit()
            thread.wait()

            # Ensure process is cleaned up
            if transcriber.process and transcriber.process.poll() is None:
                transcriber.process.terminate()
                try:
                    transcriber.process.wait(timeout=2)
                except:
                    pass

            # Process pending events to ensure cleanup
            from PyQt6.QtCore import QCoreApplication
            QCoreApplication.processEvents()
            time.sleep(0.1)


class TestRecordingTranscriberInit:
    def test_init_default_mode(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"):
            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            assert transcriber.transcription_options == transcription_options
            assert transcriber.input_device_index == 0
            assert transcriber.sample_rate == 16000
            assert transcriber.model_path == "/fake/path"
            assert transcriber.n_batch_samples == 5 * 16000
            assert transcriber.keep_sample_seconds == 0.15
            assert transcriber.is_running is False
            assert transcriber.openai_client is None

    def test_init_append_and_correct_mode(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"), \
             patch("buzz.transcriber.recording_transcriber.Settings") as mock_settings_class:
            # Mock settings to return APPEND_AND_CORRECT mode (index 2 in the enum)
            mock_settings_instance = MagicMock()
            mock_settings_class.return_value = mock_settings_instance
            # Return 2 for APPEND_AND_CORRECT mode (it's the third item in the enum)
            mock_settings_instance.value.return_value = 2

            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            # APPEND_AND_CORRECT mode should use smaller batch size and longer keep duration
            assert transcriber.n_batch_samples == 3 * 16000
            assert transcriber.keep_sample_seconds == 1.5

    def test_init_uses_default_sample_rate_when_none(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"):
            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=None,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            # Should use default whisper sample rate
            assert transcriber.sample_rate == 16000


class TestStreamCallback:
    def test_stream_callback_adds_to_queue(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"):
            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            # Create test audio data
            in_data = np.array([[0.1], [0.2], [0.3], [0.4]], dtype=np.float32)

            initial_size = transcriber.queue.size
            transcriber.stream_callback(in_data, 4, None, None)

            # Queue should have grown by 4 samples
            assert transcriber.queue.size == initial_size + 4

    def test_stream_callback_emits_amplitude_changed(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"):
            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            # Mock the amplitude_changed signal
            amplitude_values = []
            transcriber.amplitude_changed.connect(lambda amp: amplitude_values.append(amp))

            # Create test audio data
            in_data = np.array([[0.1], [0.2], [0.3], [0.4]], dtype=np.float32)
            transcriber.stream_callback(in_data, 4, None, None)

            # Should have emitted one amplitude value
            assert len(amplitude_values) == 1
            assert amplitude_values[0] > 0

    def test_stream_callback_drops_data_when_queue_full(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"):
            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            # Fill the queue beyond max_queue_size
            transcriber.queue = np.ones(transcriber.max_queue_size, dtype=np.float32)
            initial_size = transcriber.queue.size

            # Try to add more data
            in_data = np.array([[0.1], [0.2]], dtype=np.float32)
            transcriber.stream_callback(in_data, 2, None, None)

            # Queue should not have grown (data was dropped)
            assert transcriber.queue.size == initial_size


class TestStopRecording:
    def test_stop_recording_sets_is_running_false(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"):
            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            transcriber.is_running = True
            transcriber.stop_recording()

            assert transcriber.is_running is False

    def test_stop_recording_terminates_process(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"):
            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            # Mock a running process
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # Process is running
            transcriber.process = mock_process

            transcriber.stop_recording()

            # Process should have been terminated and waited
            mock_process.terminate.assert_called_once()
            mock_process.wait.assert_called_once_with(timeout=5)

    def test_stop_recording_skips_terminated_process(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"):
            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            # Mock an already terminated process
            mock_process = MagicMock()
            mock_process.poll.return_value = 0  # Process already terminated
            transcriber.process = mock_process

            transcriber.stop_recording()

            # terminate and wait should not be called
            mock_process.terminate.assert_not_called()
            mock_process.wait.assert_not_called()


class TestStartLocalWhisperServer:
    def test_start_local_whisper_server_creates_openai_client(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("time.sleep"):

            # Mock a successful process
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # Process is running
            mock_popen.return_value = mock_process

            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            try:
                transcriber.is_running = True
                transcriber.start_local_whisper_server()

                # Should have created an OpenAI client
                assert transcriber.openai_client is not None
                assert transcriber.process is not None
            finally:
                # Clean up to prevent QThread warnings
                transcriber.is_running = False
                transcriber.process = None

    def test_start_local_whisper_server_with_language(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="fr",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("time.sleep"):

            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            try:
                transcriber.is_running = True
                transcriber.start_local_whisper_server()

                # Check that the language was passed to the command
                call_args = mock_popen.call_args
                cmd = call_args[0][0]
                assert "--language" in cmd
                assert "fr" in cmd
            finally:
                transcriber.is_running = False
                transcriber.process = None

    def test_start_local_whisper_server_auto_language(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language=None,
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("time.sleep"):

            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            try:
                transcriber.is_running = True
                transcriber.start_local_whisper_server()

                # Check that auto language was used
                call_args = mock_popen.call_args
                cmd = call_args[0][0]
                assert "--language" in cmd
                assert "auto" in cmd
            finally:
                transcriber.is_running = False
                transcriber.process = None

    def test_start_local_whisper_server_handles_failure(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP),
            language="en",
            task=Task.TRANSCRIBE,
        )

        with patch("sounddevice.check_input_settings"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("time.sleep"):

            # Mock a failed process
            mock_process = MagicMock()
            mock_process.poll.return_value = 1  # Process terminated with error
            mock_process.stderr.read.return_value = b"Error loading model"
            mock_popen.return_value = mock_process

            transcriber = RecordingTranscriber(
                transcription_options=transcription_options,
                input_device_index=0,
                sample_rate=16000,
                model_path="/fake/path",
                sounddevice=MockSoundDevice(),
            )

            transcriptions = []
            transcriber.transcription.connect(lambda text: transcriptions.append(text))

            try:
                transcriber.is_running = True
                transcriber.start_local_whisper_server()

                # Should not have created a client when server failed
                assert transcriber.openai_client is None
                # Should have emitted starting and error messages
                assert len(transcriptions) >= 1
                # First message should be about starting Whisper.cpp
                assert "Whisper" in transcriptions[0]
            finally:
                transcriber.is_running = False
                transcriber.process = None
