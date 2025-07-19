import os
import sys
import time
from unittest.mock import Mock, patch

from PyQt6.QtCore import QThread

from buzz.locale import _
from buzz.assets import APP_BASE_DIR
from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.recording_transcriber import RecordingTranscriber
from buzz.transcriber.transcriber import TranscriptionOptions, Task
from tests.mock_sounddevice import MockSoundDevice
from tests.model_loader import get_model_path


class TestRecordingTranscriber:

    def test_should_transcribe(self, qtbot):
        with (patch("sounddevice.check_input_settings")):
            thread = QThread()

            transcription_model = TranscriptionModel(
                model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY
            )

            model_path = get_model_path(transcription_model)

            model_exe_path = os.path.join(APP_BASE_DIR, "whisper-server.exe")
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
