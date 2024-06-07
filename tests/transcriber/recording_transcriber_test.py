from unittest.mock import Mock, patch

from PyQt6.QtCore import QThread

from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.recording_transcriber import RecordingTranscriber
from buzz.transcriber.transcriber import TranscriptionOptions, Task
from tests.mock_sounddevice import MockInputStream
from tests.model_loader import get_model_path


class TestRecordingTranscriber:
    def test_should_transcribe(self, qtbot):
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
        )
        transcriber.moveToThread(thread)

        thread.started.connect(transcriber.start)
        thread.finished.connect(thread.deleteLater)

        mock_transcription = Mock()
        transcriber.transcription.connect(mock_transcription)

        transcriber.finished.connect(thread.quit)
        transcriber.finished.connect(transcriber.deleteLater)

        with (patch("sounddevice.InputStream", side_effect=MockInputStream),
              patch("sounddevice.check_input_settings"),
              qtbot.wait_signal(transcriber.transcription, timeout=60 * 1000)):
            thread.start()

        with qtbot.wait_signal(thread.finished, timeout=60 * 1000):
            if transcriber is not None:
                transcriber.stop_recording()

        text = mock_transcription.call_args[0][0]
        assert "Bienvenue dans Passe" in text
