from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import TranscriptionOptions, Task
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

        whisper_cpp = WhisperCpp(model=model_path)
        params = whisper_cpp.get_params(transcription_options=transcription_options)
        result = whisper_cpp.transcribe(audio=test_audio_path, params=params)

        assert "Bienvenue dans Passe" in result["text"]
