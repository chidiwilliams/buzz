import platform
import pytest

from buzz.transformers_whisper import load_model
from tests.audio import test_audio_path


@pytest.mark.skipif(
    platform.system() == "Darwin",
    reason="Not supported on Darwin",
)
class TestTransformersWhisper:
    def test_should_transcribe(self):
        model = load_model("openai/whisper-tiny")
        result = model.transcribe(
            audio=test_audio_path, language="fr", task="transcribe"
        )

        assert "Bienvenue dans Passe" in result["text"]
