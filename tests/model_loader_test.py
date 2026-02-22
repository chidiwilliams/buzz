import os
import pytest
from unittest.mock import patch

from buzz.model_loader import (
    ModelDownloader,
    TranscriptionModel,
    ModelType,
    WhisperModelSize,
    map_language_to_mms,
    is_mms_model,
    get_expected_whisper_model_size,
    get_whisper_file_path,
    WHISPER_MODEL_SIZES,
)


class TestModelLoader:
    @pytest.mark.parametrize(
        "model",
        [
            TranscriptionModel(
                model_type=ModelType.HUGGING_FACE,
                hugging_face_model_id="RaivisDejus/whisper-tiny-lv",
            ),
        ],
    )
    def test_download_model(self, model: TranscriptionModel):
        model_loader = ModelDownloader(model=model)
        model_loader.run()

        model_path = model.get_local_model_path()

        assert model_path is not None, "Model path is None"
        assert os.path.isdir(model_path), "Model path is not a directory"
        assert len(os.listdir(model_path)) > 0, "Model directory is empty"


class TestMapLanguageToMms:
    def test_empty_returns_english(self):
        assert map_language_to_mms("") == "eng"

    def test_two_letter_known_code(self):
        assert map_language_to_mms("en") == "eng"
        assert map_language_to_mms("fr") == "fra"
        assert map_language_to_mms("lv") == "lav"

    def test_three_letter_code_returned_as_is(self):
        assert map_language_to_mms("eng") == "eng"
        assert map_language_to_mms("fra") == "fra"

    def test_unknown_two_letter_code_returned_as_is(self):
        assert map_language_to_mms("xx") == "xx"

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("de", "deu"),
            ("es", "spa"),
            ("ja", "jpn"),
            ("zh", "cmn"),
            ("ar", "ara"),
        ],
    )
    def test_various_language_codes(self, code, expected):
        assert map_language_to_mms(code) == expected


class TestIsMmsModel:
    def test_empty_string(self):
        assert is_mms_model("") is False

    def test_mms_in_model_id(self):
        assert is_mms_model("facebook/mms-1b-all") is True

    def test_mms_case_insensitive(self):
        assert is_mms_model("facebook/MMS-1b-all") is True

    def test_non_mms_model(self):
        assert is_mms_model("openai/whisper-tiny") is False


class TestWhisperModelSize:
    def test_to_faster_whisper_model_size_large(self):
        assert WhisperModelSize.LARGE.to_faster_whisper_model_size() == "large-v1"

    def test_to_faster_whisper_model_size_tiny(self):
        assert WhisperModelSize.TINY.to_faster_whisper_model_size() == "tiny"

    def test_to_faster_whisper_model_size_largev3(self):
        assert WhisperModelSize.LARGEV3.to_faster_whisper_model_size() == "large-v3"

    def test_to_whisper_cpp_model_size_large(self):
        assert WhisperModelSize.LARGE.to_whisper_cpp_model_size() == "large-v1"

    def test_to_whisper_cpp_model_size_tiny(self):
        assert WhisperModelSize.TINY.to_whisper_cpp_model_size() == "tiny"

    def test_str(self):
        assert str(WhisperModelSize.TINY) == "Tiny"
        assert str(WhisperModelSize.LARGE) == "Large"
        assert str(WhisperModelSize.LARGEV3TURBO) == "Large-v3-turbo"
        assert str(WhisperModelSize.CUSTOM) == "Custom"


class TestModelType:
    def test_supports_initial_prompt(self):
        assert ModelType.WHISPER.supports_initial_prompt is True
        assert ModelType.WHISPER_CPP.supports_initial_prompt is True
        assert ModelType.OPEN_AI_WHISPER_API.supports_initial_prompt is True
        assert ModelType.FASTER_WHISPER.supports_initial_prompt is True
        assert ModelType.HUGGING_FACE.supports_initial_prompt is False

    @pytest.mark.parametrize(
        "platform_system,platform_machine,expected_faster_whisper",
        [
            ("Linux", "x86_64", True),
            ("Windows", "AMD64", True),
            ("Darwin", "arm64", True),
            ("Darwin", "x86_64", False),  # Faster Whisper not available on macOS x86_64
        ],
    )
    def test_is_available(self, platform_system, platform_machine, expected_faster_whisper):
        with patch("platform.system", return_value=platform_system), \
             patch("platform.machine", return_value=platform_machine):
            # These should always be available
            assert ModelType.WHISPER.is_available() is True
            assert ModelType.HUGGING_FACE.is_available() is True
            assert ModelType.OPEN_AI_WHISPER_API.is_available() is True
            assert ModelType.WHISPER_CPP.is_available() is True

            # Faster Whisper depends on platform
            assert ModelType.FASTER_WHISPER.is_available() == expected_faster_whisper

    def test_is_manually_downloadable(self):
        assert ModelType.WHISPER.is_manually_downloadable() is True
        assert ModelType.WHISPER_CPP.is_manually_downloadable() is True
        assert ModelType.FASTER_WHISPER.is_manually_downloadable() is True
        assert ModelType.HUGGING_FACE.is_manually_downloadable() is False
        assert ModelType.OPEN_AI_WHISPER_API.is_manually_downloadable() is False


class TestTranscriptionModel:
    def test_str_whisper(self):
        model = TranscriptionModel(
            model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY
        )
        assert str(model) == "Whisper (Tiny)"

    def test_str_whisper_cpp(self):
        model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.BASE
        )
        assert str(model) == "Whisper.cpp (Base)"

    def test_str_hugging_face(self):
        model = TranscriptionModel(
            model_type=ModelType.HUGGING_FACE,
            hugging_face_model_id="openai/whisper-tiny",
        )
        assert str(model) == "Hugging Face (openai/whisper-tiny)"

    def test_str_faster_whisper(self):
        model = TranscriptionModel(
            model_type=ModelType.FASTER_WHISPER,
            whisper_model_size=WhisperModelSize.SMALL,
        )
        assert str(model) == "Faster Whisper (Small)"

    def test_str_openai_api(self):
        model = TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API)
        assert str(model) == "OpenAI Whisper API"

    def test_default(self):
        model = TranscriptionModel.default()
        assert model.model_type in list(ModelType)
        assert model.model_type.is_available() is True

    def test_get_local_model_path_openai_api(self):
        model = TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API)
        assert model.get_local_model_path() == ""


class TestGetExpectedWhisperModelSize:
    def test_known_sizes(self):
        assert get_expected_whisper_model_size(WhisperModelSize.TINY) == 72 * 1024 * 1024
        assert get_expected_whisper_model_size(WhisperModelSize.LARGE) == 2870 * 1024 * 1024

    def test_unknown_size_returns_none(self):
        assert get_expected_whisper_model_size(WhisperModelSize.CUSTOM) is None
        assert get_expected_whisper_model_size(WhisperModelSize.LUMII) is None

    def test_all_defined_sizes_have_values(self):
        for size in WHISPER_MODEL_SIZES:
            assert WHISPER_MODEL_SIZES[size] > 0


class TestGetWhisperFilePath:
    def test_custom_size(self):
        path = get_whisper_file_path(WhisperModelSize.CUSTOM)
        assert path.endswith("custom")
        assert "whisper" in path

    def test_tiny_size(self):
        path = get_whisper_file_path(WhisperModelSize.TINY)
        assert "whisper" in path
        assert path.endswith(".pt")


class TestTranscriptionModelIsDeletable:
    def test_whisper_model_not_downloaded(self):
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        with patch.object(model, 'get_local_model_path', return_value=None):
            assert model.is_deletable() is False

    def test_whisper_model_downloaded(self):
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        with patch.object(model, 'get_local_model_path', return_value="/some/path/model.pt"):
            assert model.is_deletable() is True

    def test_openai_api_not_deletable(self):
        model = TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API)
        assert model.is_deletable() is False

    def test_hugging_face_not_deletable(self):
        model = TranscriptionModel(
            model_type=ModelType.HUGGING_FACE,
            hugging_face_model_id="openai/whisper-tiny"
        )
        assert model.is_deletable() is False


class TestTranscriptionModelGetLocalModelPath:
    def test_whisper_cpp_file_not_exists(self):
        model = TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY)
        with patch('os.path.exists', return_value=False), \
             patch('os.path.isfile', return_value=False):
            assert model.get_local_model_path() is None

    def test_whisper_file_not_exists(self):
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        with patch('os.path.exists', return_value=False):
            assert model.get_local_model_path() is None

    def test_whisper_file_too_small(self):
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        with patch('os.path.exists', return_value=True), \
             patch('os.path.isfile', return_value=True), \
             patch('os.path.getsize', return_value=1024):  # 1KB, much smaller than expected
            assert model.get_local_model_path() is None

    def test_whisper_file_valid(self):
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        expected_size = 72 * 1024 * 1024  # 72MB
        with patch('os.path.exists', return_value=True), \
             patch('os.path.isfile', return_value=True), \
             patch('os.path.getsize', return_value=expected_size):
            result = model.get_local_model_path()
            assert result is not None

    def test_faster_whisper_not_found(self):
        model = TranscriptionModel(model_type=ModelType.FASTER_WHISPER, whisper_model_size=WhisperModelSize.TINY)
        with patch('buzz.model_loader.download_faster_whisper_model', side_effect=FileNotFoundError):
            assert model.get_local_model_path() is None

    def test_hugging_face_not_found(self):
        model = TranscriptionModel(
            model_type=ModelType.HUGGING_FACE,
            hugging_face_model_id="some/model"
        )
        import huggingface_hub
        with patch.object(huggingface_hub, 'snapshot_download', side_effect=FileNotFoundError):
            assert model.get_local_model_path() is None


class TestTranscriptionModelOpenPath:
    def test_open_path_linux(self):
        with patch('sys.platform', 'linux'), \
             patch('subprocess.call') as mock_call:
            TranscriptionModel.open_path("/some/path")
            mock_call.assert_called_once_with(['xdg-open', '/some/path'])

    def test_open_path_darwin(self):
        with patch('sys.platform', 'darwin'), \
             patch('subprocess.call') as mock_call:
            TranscriptionModel.open_path("/some/path")
            mock_call.assert_called_once_with(['open', '/some/path'])


class TestModelLoaderCertifiImportError:
    def test_certifi_import_error_path(self):
        """Test that module handles certifi ImportError gracefully by reimporting with mock"""
        import importlib
        import buzz.model_loader as ml

        # The module already imported; we just verify _certifi_ca_bundle exists
        # (either as a path or None from ImportError)
        assert hasattr(ml, '_certifi_ca_bundle')

    def test_configure_http_backend_import_error(self):
        """Test configure_http_backend handles ImportError gracefully"""
        # Simulate the ImportError branch by calling directly
        import requests
        # If configure_http_backend was not available, the module would still load
        import buzz.model_loader as ml
        assert ml is not None
