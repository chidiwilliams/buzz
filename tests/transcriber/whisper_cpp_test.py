from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import (
    TranscriptionOptions,
    Task,
    FileTranscriptionTask,
    FileTranscriptionOptions,
)
from buzz.transcriber.whisper_cpp import WhisperCpp
from tests.audio import test_audio_path
from tests.model_loader import get_model_path


class TestWhisperCpp:
    def test_transcribe(self):
        transcription_options = TranscriptionOptions(
            language="fr",
            task=Task.TRANSCRIBE,
            word_level_timings=False,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            ),
        )
        model_path = get_model_path(transcription_options.model)

        task = FileTranscriptionTask(
            transcription_options=transcription_options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path=model_path,
            file_path=test_audio_path,
        )

        segments = WhisperCpp.transcribe(task=task)

        # Combine all segment texts
        full_text = " ".join(segment.text for segment in segments)
        assert "Bien venu" in full_text
