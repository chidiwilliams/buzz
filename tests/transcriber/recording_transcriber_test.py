import os
import sys
import time
import numpy as np
from unittest.mock import Mock, patch

from PyQt6.QtCore import QThread

from buzz.locale import _
from buzz.assets import APP_BASE_DIR
from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.recording_transcriber import RecordingTranscriber
from buzz.transcriber.transcriber import TranscriptionOptions, Task
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
            time.sleep(3)
