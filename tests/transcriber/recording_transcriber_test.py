import time
from unittest.mock import Mock, patch

from PyQt6.QtCore import QThread

from buzz.locale import _
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
            qtbot.waitUntil(lambda: len(transcriptions) == 3, timeout=30_000)

            assert _("Starting Whisper.cpp...") == transcriptions[0]
            assert "Bienvenue dans Passe" in transcriptions[1]

            # Wait for the thread to finish
            transcriber.stop_recording()
            thread.quit()
            thread.wait()
