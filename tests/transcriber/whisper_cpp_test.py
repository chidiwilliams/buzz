from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import TranscriptionOptions, Task
from buzz.transcriber.whisper_cpp import WhisperCpp, whisper_cpp_params
from tests.model_loader import get_model_path


class TestWhisperCpp:
    def test_transcribe(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            )
        )
        model_path = get_model_path(transcription_options.model)

        whisper_cpp = WhisperCpp(model=model_path)
        params = whisper_cpp_params(
            language="fr", task=Task.TRANSCRIBE, word_level_timings=False
        )
        result = whisper_cpp.transcribe(
            audio="testdata/whisper-french.mp3", params=params
        )

        assert "Bienvenue dans Passe" in result["text"]
