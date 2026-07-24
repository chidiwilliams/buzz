import os
import platform
import warnings
import pytest

from buzz.model_loader import ModelDownloader, ModelType, TranscriptionModel
from buzz.transformers_whisper import TransformersTranscriber
from tests.audio import test_audio_path, test_multibyte_utf8_audio_path


# These tests download real models from HuggingFace, so they only run when
# ``BUZZ_TEST_DOWNLOAD_MODELS`` is set. This keeps them out of CI (and default
# local runs) while allowing an explicit opt-in for full end-to-end checks.
pytestmark = pytest.mark.skipif(
    os.environ.get("BUZZ_TEST_DOWNLOAD_MODELS") is None,
    reason="Set BUZZ_TEST_DOWNLOAD_MODELS to run tests that download models",
)


def cached_model_path(model_id: str) -> str:
    """Download a HuggingFace model into Buzz's own cache folder and return the
    local snapshot path.

    This mirrors how the app loads models: the downloader stores files under
    ``model_root_dir`` (the Buzz cache, overridable via ``BUZZ_MODEL_ROOT``) and
    the transcriber is handed the local snapshot path rather than a repo id, so
    tests reuse the same cache instead of the default HuggingFace one.
    """
    model = TranscriptionModel(
        model_type=ModelType.HUGGING_FACE,
        hugging_face_model_id=model_id,
    )
    ModelDownloader(model=model).run()

    model_path = model.get_local_model_path()
    assert model_path is not None, f"Failed to download {model_id} into Buzz cache"
    return model_path


class TestTransformersTranscriber:
    @pytest.mark.skipif(
        platform.system() == "Darwin",
        reason="Not supported on Darwin",
    )
    def test_should_transcribe(self):
        model = TransformersTranscriber(cached_model_path("openai/whisper-tiny"))
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
    def test_should_transcribe_parakeet(self):
        model = TransformersTranscriber(cached_model_path("nvidia/parakeet-tdt-0.6b-v3"))
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
    def test_should_transcribe_vibevoice(self):
        model = TransformersTranscriber(cached_model_path("microsoft/VibeVoice-ASR-HF"))
        assert model.is_vibevoice_model is True

        result = model.transcribe(
            audio=test_multibyte_utf8_audio_path, language="lv", task="transcribe"
        )

        assert result["text"].strip() != ""
        assert len(result["segments"]) > 0

    @pytest.mark.skipif(
        platform.system() == "Darwin",
        reason="Not supported on Darwin",
    )
    def test_should_transcribe_qwen(self):
        model = TransformersTranscriber(cached_model_path("Qwen/Qwen3-ASR-1.7B-hf"))
        assert model.is_qwen_asr_model is True

        # Qwen3 ASR does not support Latvian, so use the French sample with a
        # language Qwen recognises for a meaningful end-to-end check.
        result = model.transcribe(
            audio=test_audio_path, language="fr", task="transcribe"
        )

        assert result["text"].strip() != ""
        assert len(result["segments"]) > 0
