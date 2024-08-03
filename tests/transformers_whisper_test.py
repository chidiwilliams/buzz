import platform
import pytest

from buzz.transformers_whisper import TransformersWhisper
from tests.audio import test_audio_path


class TestTransformersWhisper:
    def test_should_transcribe(self):
        model = TransformersWhisper("openai/whisper-tiny")
        result = model.transcribe(
            audio=test_audio_path, language="fr", task="transcribe"
        )

        assert "Bienvenue dans Passe" in result["text"]
