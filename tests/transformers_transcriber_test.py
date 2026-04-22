import platform
import warnings
import pytest

from buzz.transformers_whisper import TransformersTranscriber
from tests.audio import test_audio_path


class TestTransformersTranscriber:
    @pytest.mark.skipif(
        platform.system() == "Darwin",
        reason="Not supported on Darwin",
    )
    def test_should_transcribe(self):
        model = TransformersTranscriber("openai/whisper-tiny")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*inputs.*input_features.*", category=FutureWarning)
            result = model.transcribe(
                audio=test_audio_path, language="fr", task="transcribe"
            )

        assert "Bienvenue dans Passrel" in result["text"]
