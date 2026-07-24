import os
import platform
import warnings
import pytest

from buzz.transformers_whisper import TransformersTranscriber
from tests.audio import test_audio_path, test_multibyte_utf8_audio_path


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

    @pytest.mark.skipif(
        platform.system() == "Darwin",
        reason="Not supported on Darwin",
    )
    @pytest.mark.skipif(
        os.environ.get("CI") is not None,
        reason="Skip on CI to avoid downloading large Parakeet model files",
    )
    def test_should_transcribe_parakeet(self):
        model = TransformersTranscriber("nvidia/parakeet-tdt-0.6b-v3")
        assert model.is_parakeet_model is True

        result = model.transcribe(
            audio=test_multibyte_utf8_audio_path, language="lv", task="transcribe"
        )

        assert result["text"].strip() != ""
        assert len(result["segments"]) > 0

    @pytest.mark.skipif(
        platform.system() == "Darwin",
        reason="Not supported on Darwin",
    )
    @pytest.mark.skipif(
        os.environ.get("CI") is not None,
        reason="Skip on CI to avoid downloading large VibeVoice ASR model files",
    )
    def test_should_transcribe_vibevoice(self):
        model = TransformersTranscriber("microsoft/VibeVoice-ASR-HF")
        assert model.is_vibevoice_model is True

        result = model.transcribe(
            audio=test_multibyte_utf8_audio_path, language="lv", task="transcribe"
        )

        assert result["text"].strip() != ""
        assert len(result["segments"]) > 0
