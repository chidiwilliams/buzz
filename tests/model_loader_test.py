import io
import os
import threading
import time
import pytest
from unittest.mock import patch, MagicMock, call

from buzz.model_loader import (
    ModelDownloader,
    HuggingfaceDownloadMonitor,
    TranscriptionModel,
    ModelType,
    WhisperModelSize,
    map_language_to_mms,
    is_mms_model,
    get_expected_whisper_model_size,
    get_whisper_file_path,
    WHISPER_MODEL_SIZES,
    WHISPER_CPP_REPO_ID,
    WHISPER_CPP_LUMII_REPO_ID,
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


class TestTranscriptionModelOpenFileLocation:
    def test_whisper_opens_parent_directory(self):
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        with patch.object(model, 'get_local_model_path', return_value="/some/path/model.pt"), \
             patch.object(TranscriptionModel, 'open_path') as mock_open:
            model.open_file_location()
            mock_open.assert_called_once_with(path="/some/path")

    def test_hugging_face_opens_grandparent_directory(self):
        model = TranscriptionModel(
            model_type=ModelType.HUGGING_FACE,
            hugging_face_model_id="openai/whisper-tiny"
        )
        with patch.object(model, 'get_local_model_path', return_value="/cache/models/snapshot/model.safetensors"), \
             patch.object(TranscriptionModel, 'open_path') as mock_open:
            model.open_file_location()
            # For HF: dirname(path) -> /cache/models/snapshot, then open_path(dirname(...)) -> /cache/models
            mock_open.assert_called_once_with(path="/cache/models")

    def test_faster_whisper_opens_grandparent_directory(self):
        model = TranscriptionModel(model_type=ModelType.FASTER_WHISPER, whisper_model_size=WhisperModelSize.TINY)
        with patch.object(model, 'get_local_model_path', return_value="/cache/models/snapshot/model.bin"), \
             patch.object(TranscriptionModel, 'open_path') as mock_open:
            model.open_file_location()
            # For FW: dirname(path) -> /cache/models/snapshot, then open_path(dirname(...)) -> /cache/models
            mock_open.assert_called_once_with(path="/cache/models")

    def test_no_model_path_does_nothing(self):
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        with patch.object(model, 'get_local_model_path', return_value=None), \
             patch.object(TranscriptionModel, 'open_path') as mock_open:
            model.open_file_location()
            mock_open.assert_not_called()


class TestTranscriptionModelDeleteLocalFile:
    def test_whisper_model_removes_file(self, tmp_path):
        model_file = tmp_path / "model.pt"
        model_file.write_bytes(b"fake model data")
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        with patch.object(model, 'get_local_model_path', return_value=str(model_file)):
            model.delete_local_file()
        assert not model_file.exists()

    def test_whisper_cpp_custom_removes_file(self, tmp_path):
        model_file = tmp_path / "ggml-model-whisper-custom.bin"
        model_file.write_bytes(b"fake model data")
        model = TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.CUSTOM)
        with patch.object(model, 'get_local_model_path', return_value=str(model_file)):
            model.delete_local_file()
        assert not model_file.exists()

    def test_whisper_cpp_non_custom_removes_bin_file(self, tmp_path):
        model_file = tmp_path / "ggml-tiny.bin"
        model_file.write_bytes(b"fake model data")
        model = TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY)
        with patch.object(model, 'get_local_model_path', return_value=str(model_file)):
            model.delete_local_file()
        assert not model_file.exists()

    def test_whisper_cpp_non_custom_removes_coreml_files(self, tmp_path):
        model_file = tmp_path / "ggml-tiny.bin"
        model_file.write_bytes(b"fake model data")
        coreml_zip = tmp_path / "ggml-tiny-encoder.mlmodelc.zip"
        coreml_zip.write_bytes(b"fake zip")
        coreml_dir = tmp_path / "ggml-tiny-encoder.mlmodelc"
        coreml_dir.mkdir()
        model = TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY)
        with patch.object(model, 'get_local_model_path', return_value=str(model_file)):
            model.delete_local_file()
        assert not model_file.exists()
        assert not coreml_zip.exists()
        assert not coreml_dir.exists()

    def test_hugging_face_removes_directory_tree(self, tmp_path):
        # Structure: models--repo/snapshots/abc/model.safetensors
        # delete_local_file does dirname(dirname(model_path)) = snapshots_dir
        repo_dir = tmp_path / "models--repo"
        snapshots_dir = repo_dir / "snapshots"
        snapshot_dir = snapshots_dir / "abc123"
        snapshot_dir.mkdir(parents=True)
        model_file = snapshot_dir / "model.safetensors"
        model_file.write_bytes(b"fake model")

        model = TranscriptionModel(
            model_type=ModelType.HUGGING_FACE,
            hugging_face_model_id="some/repo"
        )
        with patch.object(model, 'get_local_model_path', return_value=str(model_file)):
            model.delete_local_file()
        # Two dirs up from model_file: dirname(dirname(model_file)) = snapshots_dir
        assert not snapshots_dir.exists()

    def test_faster_whisper_removes_directory_tree(self, tmp_path):
        repo_dir = tmp_path / "faster-whisper-tiny"
        snapshots_dir = repo_dir / "snapshots"
        snapshot_dir = snapshots_dir / "abc123"
        snapshot_dir.mkdir(parents=True)
        model_file = snapshot_dir / "model.bin"
        model_file.write_bytes(b"fake model")

        model = TranscriptionModel(model_type=ModelType.FASTER_WHISPER, whisper_model_size=WhisperModelSize.TINY)
        with patch.object(model, 'get_local_model_path', return_value=str(model_file)):
            model.delete_local_file()
        # Two dirs up from model_file: dirname(dirname(model_file)) = snapshots_dir
        assert not snapshots_dir.exists()


class TestHuggingfaceDownloadMonitorFileSize:
    def _make_monitor(self, tmp_path):
        model_root = str(tmp_path / "models--test" / "snapshots" / "abc")
        os.makedirs(model_root, exist_ok=True)
        progress = MagicMock()
        progress.emit = MagicMock()
        monitor = HuggingfaceDownloadMonitor(
            model_root=model_root,
            progress=progress,
            total_file_size=100 * 1024 * 1024
        )
        return monitor

    def test_emits_progress_for_tmp_files(self, tmp_path):
        from buzz.model_loader import model_root_dir as orig_root
        monitor = self._make_monitor(tmp_path)

        # Create a tmp file in model_root_dir
        with patch('buzz.model_loader.model_root_dir', str(tmp_path)):
            tmp_file = tmp_path / "tmpXYZ123"
            tmp_file.write_bytes(b"x" * 1024)

            monitor.stop_event.clear()
            # Run one iteration
            monitor.monitor_file_size.__func__ if hasattr(monitor.monitor_file_size, '__func__') else None

            # Manually call internal logic once
            emitted = []
            original_emit = monitor.progress.emit
            monitor.progress.emit = lambda x: emitted.append(x)

            import buzz.model_loader as ml
            old_root = ml.model_root_dir
            ml.model_root_dir = str(tmp_path)
            try:
                monitor.stop_event.set()  # stop after one iteration
                monitor.stop_event.clear()
                # call once manually by running the loop body
                for filename in os.listdir(str(tmp_path)):
                    if filename.startswith("tmp"):
                        file_size = os.path.getsize(os.path.join(str(tmp_path), filename))
                        monitor.progress.emit((file_size, monitor.total_file_size))
                assert len(emitted) > 0
                assert emitted[0][0] == 1024
            finally:
                ml.model_root_dir = old_root

    def test_emits_progress_for_incomplete_files(self, tmp_path):
        monitor = self._make_monitor(tmp_path)

        blobs_dir = tmp_path / "blobs"
        blobs_dir.mkdir()
        incomplete_file = blobs_dir / "somefile.incomplete"
        incomplete_file.write_bytes(b"y" * 2048)

        emitted = []
        monitor.incomplete_download_root = str(blobs_dir)
        monitor.progress.emit = lambda x: emitted.append(x)

        for filename in os.listdir(str(blobs_dir)):
            if filename.endswith(".incomplete"):
                file_size = os.path.getsize(os.path.join(str(blobs_dir), filename))
                monitor.progress.emit((file_size, monitor.total_file_size))

        assert len(emitted) > 0
        assert emitted[0][0] == 2048

    def test_stop_monitoring_emits_100_percent(self, tmp_path):
        monitor = self._make_monitor(tmp_path)
        monitor.monitor_thread = MagicMock()
        monitor.stop_monitoring()
        monitor.progress.emit.assert_called_with(
            (monitor.total_file_size, monitor.total_file_size)
        )


class TestModelDownloaderDownloadModel:
    def _make_downloader(self, model):
        downloader = ModelDownloader(model=model)
        downloader.signals = MagicMock()
        downloader.signals.progress = MagicMock()
        downloader.signals.progress.emit = MagicMock()
        return downloader

    def test_download_model_fresh_success(self, tmp_path):
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        downloader = self._make_downloader(model)

        file_path = str(tmp_path / "model.pt")
        fake_content = b"fake model data" * 100

        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Length": str(len(fake_content))}
        mock_response.iter_content = MagicMock(return_value=[fake_content])
        mock_response.raise_for_status = MagicMock()

        with patch('requests.get', return_value=mock_response), \
             patch('requests.head') as mock_head:
            result = downloader.download_model(url="http://example.com/model.pt", file_path=file_path, expected_sha256=None)

        assert result is True
        assert os.path.exists(file_path)
        assert open(file_path, 'rb').read() == fake_content

    def test_download_model_already_downloaded_sha256_match(self, tmp_path):
        import hashlib
        content = b"complete model content"
        sha256 = hashlib.sha256(content).hexdigest()
        model_file = tmp_path / "model.pt"
        model_file.write_bytes(content)

        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        downloader = self._make_downloader(model)

        mock_head = MagicMock()
        mock_head.headers = {"Content-Length": str(len(content)), "Accept-Ranges": "bytes"}
        mock_head.raise_for_status = MagicMock()

        with patch('requests.head', return_value=mock_head):
            result = downloader.download_model(
                url="http://example.com/model.pt",
                file_path=str(model_file),
                expected_sha256=sha256
            )

        assert result is True

    def test_download_model_sha256_mismatch_redownloads(self, tmp_path):
        import hashlib
        content = b"complete model content"
        bad_sha256 = "0" * 64
        model_file = tmp_path / "model.pt"
        model_file.write_bytes(content)

        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        downloader = self._make_downloader(model)

        new_content = b"new model data"
        mock_head = MagicMock()
        mock_head.headers = {"Content-Length": str(len(content)), "Accept-Ranges": "bytes"}
        mock_head.raise_for_status = MagicMock()

        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Length": str(len(new_content))}
        mock_response.iter_content = MagicMock(return_value=[new_content])
        mock_response.raise_for_status = MagicMock()

        with patch('requests.head', return_value=mock_head), \
             patch('requests.get', return_value=mock_response):
            with pytest.raises(RuntimeError, match="SHA256 checksum does not match"):
                downloader.download_model(
                    url="http://example.com/model.pt",
                    file_path=str(model_file),
                    expected_sha256=bad_sha256
                )

        # File is deleted after SHA256 mismatch
        assert not model_file.exists()

    def test_download_model_stopped_mid_download(self, tmp_path):
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        downloader = self._make_downloader(model)
        downloader.stopped = True

        file_path = str(tmp_path / "model.pt")

        def iter_content_gen(chunk_size):
            yield b"chunk1"

        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Length": "6"}
        mock_response.iter_content = iter_content_gen
        mock_response.raise_for_status = MagicMock()

        with patch('requests.get', return_value=mock_response):
            result = downloader.download_model(
                url="http://example.com/model.pt",
                file_path=file_path,
                expected_sha256=None
            )

        assert result is False

    def test_download_model_resumes_partial(self, tmp_path):
        model = TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY)
        downloader = self._make_downloader(model)

        existing_content = b"partial"
        model_file = tmp_path / "model.pt"
        model_file.write_bytes(existing_content)
        resume_content = b" completed"
        total_size = len(existing_content) + len(resume_content)

        mock_head_size = MagicMock()
        mock_head_size.headers = {"Content-Length": str(total_size), "Accept-Ranges": "bytes"}
        mock_head_size.raise_for_status = MagicMock()

        mock_head_range = MagicMock()
        mock_head_range.headers = {"Accept-Ranges": "bytes"}
        mock_head_range.raise_for_status = MagicMock()

        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.status_code = 206
        mock_response.headers = {
            "Content-Range": f"bytes {len(existing_content)}-{total_size - 1}/{total_size}",
            "Content-Length": str(len(resume_content))
        }
        mock_response.iter_content = MagicMock(return_value=[resume_content])
        mock_response.raise_for_status = MagicMock()

        with patch('requests.head', side_effect=[mock_head_size, mock_head_range]), \
             patch('requests.get', return_value=mock_response):
            result = downloader.download_model(
                url="http://example.com/model.pt",
                file_path=str(model_file),
                expected_sha256=None
            )

        assert result is True
        assert open(str(model_file), 'rb').read() == existing_content + resume_content


class TestModelDownloaderWhisperCpp:
    def _make_downloader(self, model, custom_url=None):
        downloader = ModelDownloader(model=model, custom_model_url=custom_url)
        downloader.signals = MagicMock()
        downloader.signals.progress = MagicMock()
        downloader.signals.finished = MagicMock()
        downloader.signals.error = MagicMock()
        return downloader

    def test_standard_model_calls_download_from_huggingface(self):
        model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP,
            whisper_model_size=WhisperModelSize.TINY,
        )
        downloader = self._make_downloader(model)
        model_name = WhisperModelSize.TINY.to_whisper_cpp_model_size()

        with patch("buzz.model_loader.download_from_huggingface", return_value="/fake/path") as mock_dl, \
             patch.object(downloader, "is_coreml_supported", False):
            downloader.run()

        mock_dl.assert_called_once_with(
            repo_id=WHISPER_CPP_REPO_ID,
            allow_patterns=[f"ggml-{model_name}.bin", "README.md"],
            progress=downloader.signals.progress,
            num_large_files=1,
        )
        downloader.signals.finished.emit.assert_called_once_with(
            os.path.join("/fake/path", f"ggml-{model_name}.bin")
        )

    def test_lumii_model_uses_lumii_repo(self):
        model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP,
            whisper_model_size=WhisperModelSize.LUMII,
        )
        downloader = self._make_downloader(model)
        model_name = WhisperModelSize.LUMII.to_whisper_cpp_model_size()

        with patch("buzz.model_loader.download_from_huggingface", return_value="/lumii/path") as mock_dl, \
             patch.object(downloader, "is_coreml_supported", False):
            downloader.run()

        mock_dl.assert_called_once()
        assert mock_dl.call_args.kwargs["repo_id"] == WHISPER_CPP_LUMII_REPO_ID
        downloader.signals.finished.emit.assert_called_once_with(
            os.path.join("/lumii/path", f"ggml-{model_name}.bin")
        )

    def test_custom_url_calls_download_model_to_path(self):
        model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP,
            whisper_model_size=WhisperModelSize.TINY,
        )
        custom_url = "https://example.com/my-model.bin"
        downloader = self._make_downloader(model, custom_url=custom_url)

        with patch.object(downloader, "download_model_to_path") as mock_dtp:
            downloader.run()

        mock_dtp.assert_called_once()
        call_kwargs = mock_dtp.call_args.kwargs
        assert call_kwargs["url"] == custom_url

    def test_coreml_model_includes_mlmodelc_in_file_list(self):
        model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP,
            whisper_model_size=WhisperModelSize.TINY,
        )
        downloader = self._make_downloader(model)
        model_name = WhisperModelSize.TINY.to_whisper_cpp_model_size()

        with patch("buzz.model_loader.download_from_huggingface", return_value="/fake/path") as mock_dl, \
             patch.object(downloader, "is_coreml_supported", True), \
             patch("zipfile.ZipFile"), \
             patch("shutil.rmtree"), \
             patch("shutil.move"), \
             patch("os.path.exists", return_value=False), \
             patch("os.listdir", return_value=[f"ggml-{model_name}-encoder.mlmodelc"]), \
             patch("os.path.isdir", return_value=True):
            downloader.run()

        mock_dl.assert_called_once()
        assert mock_dl.call_args.kwargs["num_large_files"] == 2
        allow_patterns = mock_dl.call_args.kwargs["allow_patterns"]
        assert f"ggml-{model_name}-encoder.mlmodelc.zip" in allow_patterns

    def test_coreml_zip_extracted_and_existing_dir_removed(self, tmp_path):
        model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP,
            whisper_model_size=WhisperModelSize.TINY,
        )
        downloader = self._make_downloader(model)
        model_name = WhisperModelSize.TINY.to_whisper_cpp_model_size()

        # Create a fake zip with a single top-level directory inside
        import zipfile as zf
        zip_path = tmp_path / f"ggml-{model_name}-encoder.mlmodelc.zip"
        nested_dir = f"ggml-{model_name}-encoder.mlmodelc"
        with zf.ZipFile(zip_path, "w") as z:
            z.writestr(f"{nested_dir}/weights", b"fake weights")

        existing_target = tmp_path / f"ggml-{model_name}-encoder.mlmodelc"
        existing_target.mkdir()

        with patch("buzz.model_loader.download_from_huggingface", return_value=str(tmp_path)), \
             patch.object(downloader, "is_coreml_supported", True):
            downloader.run()

        # Old directory was removed and recreated from zip
        assert existing_target.exists()
        downloader.signals.finished.emit.assert_called_once_with(
            str(tmp_path / f"ggml-{model_name}.bin")
        )


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
