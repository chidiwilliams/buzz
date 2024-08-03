import platform
import pytest
import time
import gc

from buzz.transformers_whisper import TransformersWhisper
from tests.audio import test_audio_path


class TestTransformersWhisper:
    # @pytest.mark.skipif(
    #     platform.system() == "Darwin",
    #     reason="Not supported on Darwin",
    # )
    def test_should_transcribe(self):
        model = TransformersWhisper("openai/whisper-tiny")
        result = model.transcribe(
            audio=test_audio_path, language="fr", task="transcribe"
        )

        assert "Bienvenue dans Passe" in result["text"]

        # Cleanup
        del model
        del result
        gc.collect()

        time.sleep(5)
