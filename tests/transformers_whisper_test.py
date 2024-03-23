import sys

import pytest

from buzz.transformers_whisper import load_model
from tests.audio import test_audio_path


@pytest.mark.skipif(sys.platform == "linux", reason="Not supported on Linux")
class TestTransformersWhisper:
    def test_should_transcribe(self):
        model = load_model("openai/whisper-tiny")
        result = model.transcribe(
            audio=test_audio_path, language="fr", task="transcribe"
        )

        assert "Bienvenue dans Passe" in result["text"]
