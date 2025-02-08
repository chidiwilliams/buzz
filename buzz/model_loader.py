import enum
import hashlib
import logging
import os
import time
import threading
import shutil
import subprocess
import sys
import tempfile
import warnings
import platform
import requests
import whisper
import huggingface_hub
import zipfile
from dataclasses import dataclass
from typing import Optional, List

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable
from platformdirs import user_cache_dir
from huggingface_hub.errors import LocalEntryNotFoundError

from buzz.locale import _

# Catch exception from whisper.dll not getting loaded.
# TODO: Remove flag and try-except when issue with loading
# the DLL in some envs is fixed.
LOADED_WHISPER_CPP_BINARY = False
try:
    import buzz.whisper_cpp as whisper_cpp  # noqa: F401

    LOADED_WHISPER_CPP_BINARY = True
except ImportError:
    logging.exception("")

model_root_dir = user_cache_dir("Buzz")
model_root_dir = os.path.join(model_root_dir, "models")
model_root_dir = os.getenv("BUZZ_MODEL_ROOT", model_root_dir)
os.makedirs(model_root_dir, exist_ok=True)

logging.debug("Model root directory: %s", model_root_dir)


class WhisperModelSize(str, enum.Enum):
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    LARGEV2 = "large-v2"
    LARGEV3 = "large-v3"
    LARGEV3TURBO = "large-v3-turbo"
    CUSTOM = "custom"

    def to_faster_whisper_model_size(self) -> str:
        if self == WhisperModelSize.LARGE:
            return "large-v1"
        return self.value

    def to_whisper_cpp_model_size(self) -> str:
        if self == WhisperModelSize.LARGE:
            return "large-v1"
        return self.value

    def __str__(self):
        return self.value.capitalize()


class ModelType(enum.Enum):
    WHISPER = "Whisper"
    WHISPER_CPP = "Whisper.cpp"
    HUGGING_FACE = "Hugging Face"
    FASTER_WHISPER = "Faster Whisper"
    OPEN_AI_WHISPER_API = "OpenAI Whisper API"

    @property
    def supports_initial_prompt(self):
        return self in (
            ModelType.WHISPER,
            ModelType.WHISPER_CPP,
            ModelType.OPEN_AI_WHISPER_API,
            ModelType.FASTER_WHISPER,
        )

    def is_available(self):
        if (
            # Hide Whisper.cpp option if whisper.dll did not load correctly.
            # See: https://github.com/chidiwilliams/buzz/issues/274,
            # https://github.com/chidiwilliams/buzz/issues/197
            (self == ModelType.WHISPER_CPP and not LOADED_WHISPER_CPP_BINARY)
        ):
            return False
        elif (
            # Hide Faster Whisper option on macOS x86_64
            # See: https://github.com/SYSTRAN/faster-whisper/issues/541
            (self == ModelType.FASTER_WHISPER
                and platform.system() == "Darwin" and platform.machine() == "x86_64")
        ):
            return False
        return True

    def is_manually_downloadable(self):
        return self in (
            ModelType.WHISPER,
            ModelType.WHISPER_CPP,
            ModelType.FASTER_WHISPER,
        )


HUGGING_FACE_MODEL_ALLOW_PATTERNS = [
    "model.safetensors",  # largest by size first
    "pytorch_model.bin",
    "model-00001-of-00002.safetensors",
    "model-00002-of-00002.safetensors",
    "model.safetensors.index.json",
    "added_tokens.json",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "normalizer.json",
    "preprocessor_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
]


@dataclass()
class TranscriptionModel:
    def __init__(
        self,
        model_type: ModelType = ModelType.WHISPER,
        whisper_model_size: Optional[WhisperModelSize] = WhisperModelSize.TINY,
        hugging_face_model_id: Optional[str] = ""
    ):
        self.model_type = model_type
        self.whisper_model_size = whisper_model_size
        self.hugging_face_model_id = hugging_face_model_id

    def __str__(self):
        match self.model_type:
            case ModelType.WHISPER:
                return f"Whisper ({self.whisper_model_size})"
            case ModelType.WHISPER_CPP:
                return f"Whisper.cpp ({self.whisper_model_size})"
            case ModelType.HUGGING_FACE:
                return f"Hugging Face ({self.hugging_face_model_id})"
            case ModelType.FASTER_WHISPER:
                return f"Faster Whisper ({self.whisper_model_size})"
            case ModelType.OPEN_AI_WHISPER_API:
                return "OpenAI Whisper API"
            case _:
                raise Exception("Unknown model type")

    def is_deletable(self):
        return (
            self.model_type == ModelType.WHISPER
            or self.model_type == ModelType.WHISPER_CPP
            or self.model_type == ModelType.FASTER_WHISPER
        ) and self.get_local_model_path() is not None

    def open_file_location(self):
        model_path = self.get_local_model_path()

        if (self.model_type == ModelType.HUGGING_FACE
                or self.model_type == ModelType.FASTER_WHISPER):
            model_path = os.path.dirname(model_path)

        if model_path is None:
            return
        self.open_path(path=os.path.dirname(model_path))

    @staticmethod
    def default():
        model_type = next(
            model_type for model_type in ModelType if model_type.is_available()
        )
        return TranscriptionModel(model_type=model_type)

    @staticmethod
    def open_path(path: str):
        if sys.platform == "win32":
            os.startfile(path)
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, path])

    def delete_local_file(self):
        model_path = self.get_local_model_path()

        if (self.model_type == ModelType.HUGGING_FACE
                or self.model_type == ModelType.FASTER_WHISPER):
            model_path = os.path.dirname(os.path.dirname(model_path))

            logging.debug("Deleting model directory: %s", model_path)

            shutil.rmtree(model_path, ignore_errors=True)
            return

        logging.debug("Deleting model file: %s", model_path)
        os.remove(model_path)

    def get_local_model_path(self) -> Optional[str]:
        if self.model_type == ModelType.WHISPER_CPP:
            file_path = get_whisper_cpp_file_path(size=self.whisper_model_size)
            if not file_path or not os.path.exists(file_path) or not os.path.isfile(file_path):
                return None
            return file_path

        if self.model_type == ModelType.WHISPER:
            file_path = get_whisper_file_path(size=self.whisper_model_size)
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                return None
            return file_path

        if self.model_type == ModelType.FASTER_WHISPER:
            try:
                return download_faster_whisper_model(
                    model=self, local_files_only=True
                )
            except (ValueError, FileNotFoundError):
                return None

        if self.model_type == ModelType.OPEN_AI_WHISPER_API:
            return ""

        if self.model_type == ModelType.HUGGING_FACE:
            try:
                return huggingface_hub.snapshot_download(
                    self.hugging_face_model_id,
                    allow_patterns=HUGGING_FACE_MODEL_ALLOW_PATTERNS,
                    local_files_only=True,
                    cache_dir=model_root_dir,
                    etag_timeout=60
                )
            except (ValueError, FileNotFoundError):
                return None

        raise Exception("Unknown model type")


WHISPER_CPP_REPO_ID = "ggerganov/whisper.cpp"


def get_whisper_cpp_file_path(size: WhisperModelSize) -> str:
    if size == WhisperModelSize.CUSTOM:
        return os.path.join(model_root_dir, f"ggml-model-whisper-custom.bin")

    model_filename = f"ggml-{size.to_whisper_cpp_model_size()}.bin"

    try:
        model_path =  huggingface_hub.snapshot_download(
            repo_id=WHISPER_CPP_REPO_ID,
            allow_patterns=[model_filename],
            local_files_only=True,
            cache_dir=model_root_dir,
            etag_timeout=60
        )

        return os.path.join(model_path, model_filename)
    except LocalEntryNotFoundError:
        return ''


def get_whisper_file_path(size: WhisperModelSize) -> str:
    root_dir = os.path.join(model_root_dir, "whisper")

    if size == WhisperModelSize.CUSTOM:
        return os.path.join(root_dir, "custom")

    url = whisper._MODELS[size.value]
    return os.path.join(root_dir, os.path.basename(url))


class HuggingfaceDownloadMonitor:
    def __init__(self, model_root: str, progress: pyqtSignal(tuple), total_file_size: int):
        self.model_root = model_root
        self.progress = progress
        self.total_file_size = total_file_size
        self.incomplete_download_root = None
        self.stop_event = threading.Event()
        self.monitor_thread = None
        self.set_download_roots()

    def set_download_roots(self):
        normalized_model_root = os.path.normpath(self.model_root)
        two_dirs_up = os.path.normpath(os.path.join(normalized_model_root, "..", ".."))
        self.incomplete_download_root = os.path.normpath(os.path.join(two_dirs_up, "blobs"))

    def clean_tmp_files(self):
        for filename in os.listdir(model_root_dir):
            if filename.startswith("tmp"):
                os.remove(os.path.join(model_root_dir, filename))

    def monitor_file_size(self):
        while not self.stop_event.is_set():
            if model_root_dir is not None:
                for filename in os.listdir(model_root_dir):
                    if filename.startswith("tmp"):
                        file_size = os.path.getsize(os.path.join(model_root_dir, filename))
                        self.progress.emit((file_size, self.total_file_size))

            for filename in os.listdir(self.incomplete_download_root):
                if filename.endswith(".incomplete"):
                    file_size = os.path.getsize(os.path.join(self.incomplete_download_root, filename))
                    self.progress.emit((file_size, self.total_file_size))

            time.sleep(2)

    def start_monitoring(self):
        self.clean_tmp_files()
        self.monitor_thread = threading.Thread(target=self.monitor_file_size)
        self.monitor_thread.start()

    def stop_monitoring(self):
        self.progress.emit((self.total_file_size, self.total_file_size))

        if self.monitor_thread is not None:
            self.stop_event.set()
            self.monitor_thread.join()


def get_file_size(url):
    response = requests.head(url, allow_redirects=True)
    response.raise_for_status()
    return int(response.headers['Content-Length'])


def download_from_huggingface(
        repo_id: str,
        allow_patterns: List[str],
        progress: pyqtSignal(tuple),
        num_large_files: int = 1
):
    progress.emit((0, 100))

    try:
        model_root = huggingface_hub.snapshot_download(
            repo_id,
            allow_patterns=allow_patterns[num_large_files:],  # all, but largest
            cache_dir=model_root_dir,
            etag_timeout=60
        )
    except Exception as exc:
        logging.exception(exc)
        return ""

    progress.emit((1, 100))

    largest_file_size = 0
    for pattern in allow_patterns[:num_large_files]:
        try:
            file_url = huggingface_hub.hf_hub_url(repo_id, pattern)
            file_size = get_file_size(file_url)

            if file_size > largest_file_size:
                largest_file_size = file_size

        except requests.exceptions.RequestException as e:
            continue

    model_download_monitor = HuggingfaceDownloadMonitor(model_root, progress, largest_file_size)
    model_download_monitor.start_monitoring()

    try:
        huggingface_hub.snapshot_download(
            repo_id,
            allow_patterns=allow_patterns[:num_large_files],  # largest
            cache_dir=model_root_dir,
            etag_timeout=60
        )
    except Exception as exc:
        logging.exception(exc)
        model_download_monitor.stop_monitoring()
        # Cleanup to prevent incomplete downloads errors
        if os.path.exists(model_root):
            shutil.rmtree(model_root)
        return ""

    model_download_monitor.stop_monitoring()

    return model_root


def download_faster_whisper_model(
    model: TranscriptionModel, local_files_only=False, progress: pyqtSignal(tuple) = None
):
    size = model.whisper_model_size.to_faster_whisper_model_size()
    custom_repo_id = model.hugging_face_model_id

    if size == WhisperModelSize.CUSTOM and custom_repo_id == "":
        raise ValueError("Custom model id is not provided")

    if size == WhisperModelSize.CUSTOM:
        repo_id = custom_repo_id
    # Replicating models from faster-whisper code https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/utils.py#L29
    # Changes to turbo model also in whisper_file_transcriber.py
    elif size == WhisperModelSize.LARGEV3TURBO:
        repo_id = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    else:
        repo_id = "Systran/faster-whisper-%s" % size

    allow_patterns = [
        "model.bin",  # largest by size first
        "pytorch_model.bin",  # possible alternative model filename
        "config.json",
        "tokenizer.json",
        "vocabulary.*",
    ]

    if local_files_only:
        return huggingface_hub.snapshot_download(
            repo_id,
            allow_patterns=allow_patterns,
            local_files_only=True,
            cache_dir=model_root_dir,
            etag_timeout=60
        )

    return download_from_huggingface(
        repo_id,
        allow_patterns=allow_patterns,
        progress=progress,
        num_large_files=2
    )


class ModelDownloader(QRunnable):
    class Signals(QObject):
        finished = pyqtSignal(str)
        progress = pyqtSignal(tuple)  # (current, total)
        error = pyqtSignal(str)

    def __init__(self, model: TranscriptionModel, custom_model_url: Optional[str] = None):
        super().__init__()

        self.is_coreml_supported = platform.system() == "Darwin" and platform.machine() == "arm64"
        self.signals = self.Signals()
        self.model = model
        self.stopped = False
        self.custom_model_url = custom_model_url

    def run(self) -> None:
        logging.debug("Downloading model: %s, %s", self.model, self.model.hugging_face_model_id)

        if self.model.model_type == ModelType.WHISPER_CPP:
            if self.custom_model_url:
                url = self.custom_model_url
                file_path = get_whisper_cpp_file_path(size=self.model.whisper_model_size)
                return self.download_model_to_path(url=url, file_path=file_path)

            model_name = self.model.whisper_model_size.to_whisper_cpp_model_size()

            whisper_cpp_model_files = [
                f"ggml-{model_name}.bin",
                "README.md"
            ]
            num_large_files = 1
            if self.is_coreml_supported:
                whisper_cpp_model_files = [
                        f"ggml-{model_name}.bin",
                        f"ggml-{model_name}-encoder.mlmodelc.zip",
                        "README.md"
                ]
                num_large_files = 2

            model_path = download_from_huggingface(
                repo_id=WHISPER_CPP_REPO_ID,
                allow_patterns=whisper_cpp_model_files,
                progress=self.signals.progress,
                num_large_files=num_large_files
            )

            if self.is_coreml_supported:
                with zipfile.ZipFile(
                        os.path.join(model_path, f"ggml-{model_name}-encoder.mlmodelc.zip"), 'r') as zip_ref:
                    zip_ref.extractall(model_path)

            self.signals.finished.emit(os.path.join(model_path, f"ggml-{model_name}.bin"))
            return

        if self.model.model_type == ModelType.WHISPER:
            url = whisper._MODELS[self.model.whisper_model_size.value]
            file_path = get_whisper_file_path(size=self.model.whisper_model_size)
            expected_sha256 = url.split("/")[-2]
            return self.download_model_to_path(
                url=url, file_path=file_path, expected_sha256=expected_sha256
            )

        if self.model.model_type == ModelType.FASTER_WHISPER:
            model_path = download_faster_whisper_model(
                model=self.model,
                progress=self.signals.progress,
            )

            if model_path == "":
                self.signals.error.emit(_("Error"))

            self.signals.finished.emit(model_path)
            return

        if self.model.model_type == ModelType.HUGGING_FACE:
            model_path = download_from_huggingface(
                self.model.hugging_face_model_id,
                allow_patterns=HUGGING_FACE_MODEL_ALLOW_PATTERNS,
                progress=self.signals.progress,
                num_large_files=4
            )
            self.signals.finished.emit(model_path)
            return

        if self.model.model_type == ModelType.OPEN_AI_WHISPER_API:
            self.signals.finished.emit("")
            return

        raise Exception("Invalid model type: " + self.model.model_type.value)

    def download_model_to_path(
        self, url: str, file_path: str, expected_sha256: Optional[str] = None
    ):
        try:
            downloaded = self.download_model(url, file_path, expected_sha256)
            if downloaded:
                self.signals.finished.emit(file_path)
        except requests.RequestException:
            self.signals.error.emit(_("A connection error occurred"))
            if os.path.exists(file_path):
                os.remove(file_path)
            logging.exception("")
        except Exception as exc:
            self.signals.error.emit(str(exc))
            if os.path.exists(file_path):
                os.remove(file_path)
            logging.exception(exc)

    def download_model(
        self, url: str, file_path: str, expected_sha256: Optional[str]
    ) -> bool:
        logging.debug(f"Downloading model from {url} to {file_path}")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        if os.path.exists(file_path) and not os.path.isfile(file_path):
            raise RuntimeError(f"{file_path} exists and is not a regular file")

        if os.path.isfile(file_path):
            if expected_sha256 is None:
                return True

            model_bytes = open(file_path, "rb").read()
            model_sha256 = hashlib.sha256(model_bytes).hexdigest()
            if model_sha256 == expected_sha256:
                return True
            else:
                warnings.warn(
                    f"{file_path} exists, but the SHA256 checksum does not match; re-downloading the file"
                )

        tmp_file = tempfile.mktemp()
        logging.debug("Downloading to temporary file = %s", tmp_file)

        # Downloads the model using the requests module instead of urllib to
        # use the certs from certifi when the app is running in frozen mode
        with requests.get(url, stream=True, timeout=15) as source, open(
            tmp_file, "wb"
        ) as output:
            source.raise_for_status()
            total_size = float(source.headers.get("Content-Length", 0))
            current = 0.0
            self.signals.progress.emit((current, total_size))
            for chunk in source.iter_content(chunk_size=8192):
                if self.stopped:
                    return False
                output.write(chunk)
                current += len(chunk)
                self.signals.progress.emit((current, total_size))

        if expected_sha256 is not None:
            model_bytes = open(tmp_file, "rb").read()
            if hashlib.sha256(model_bytes).hexdigest() != expected_sha256:
                raise RuntimeError(
                    "Model has been downloaded but the SHA256 checksum does not match. Please retry loading the "
                    "model."
                )

        logging.debug("Downloaded model")

        # https://github.com/chidiwilliams/buzz/issues/454
        shutil.move(tmp_file, file_path)
        logging.debug("Moved file from %s to %s", tmp_file, file_path)
        return True

    def cancel(self):
        self.stopped = True


def get_custom_api_whisper_model(base_url: str):
    if "api.groq.com" in base_url:
        return "whisper-large-v3"

    return "whisper-1"
