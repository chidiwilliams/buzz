import platform
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
        result = model.transcribe(
            audio=test_audio_path, language="fr", task="transcribe"
        )

        assert "Bienvenue dans Passrel" in result["text"]
