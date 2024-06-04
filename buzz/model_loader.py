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
from dataclasses import dataclass
from typing import Optional, List

import requests
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable
from platformdirs import user_cache_dir

import faster_whisper
import whisper
import huggingface_hub

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
os.makedirs(model_root_dir, exist_ok=True)

logging.debug("Model root directory: %s", model_root_dir)

class WhisperModelSize(str, enum.Enum):
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"

    def to_faster_whisper_model_size(self) -> str:
        if self == WhisperModelSize.LARGE:
            return "large-v2"
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

    def supports_recording(self):
        # Live transcription with OpenAI Whisper API not supported
        return self != ModelType.OPEN_AI_WHISPER_API

    def is_available(self):
        if (
            # Hide Whisper.cpp option if whisper.dll did not load correctly.
            # See: https://github.com/chidiwilliams/buzz/issues/274,
            # https://github.com/chidiwilliams/buzz/issues/197
            (self == ModelType.WHISPER_CPP and not LOADED_WHISPER_CPP_BINARY)
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
    model_type: ModelType = ModelType.WHISPER
    whisper_model_size: Optional[WhisperModelSize] = WhisperModelSize.TINY
    hugging_face_model_id: Optional[str] = None

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
        ) and self.get_local_model_path() is not None

    def open_file_location(self):
        model_path = self.get_local_model_path()
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
        os.remove(model_path)

    def get_local_model_path(self) -> Optional[str]:
        if self.model_type == ModelType.WHISPER_CPP:
            file_path = get_whisper_cpp_file_path(size=self.whisper_model_size)
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
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
                    size=self.whisper_model_size.value, local_files_only=True
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
                    cache_dir=model_root_dir
                )
            except (ValueError, FileNotFoundError):
                return None

        raise Exception("Unknown model type")


WHISPER_CPP_MODELS_SHA256 = {
    "tiny": "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
    "base": "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
    "small": "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
    "medium": "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208",
    "large": "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2",
}


def get_whisper_cpp_file_path(size: WhisperModelSize) -> str:
    return os.path.join(model_root_dir, f"ggml-model-whisper-{size.value}.bin")


def get_whisper_file_path(size: WhisperModelSize) -> str:
    root_dir = os.getenv(
        "XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    )
    url = whisper._MODELS[size.value]
    return os.path.join(root_dir, os.path.basename(url))


class HuggingfaceDownloadMonitor:
    def __init__(self, model_root: str, progress: pyqtSignal(tuple), total_file_size: int):
        self.model_root = model_root
        self.progress = progress
        self.total_file_size = total_file_size
        self.tmp_download_root = None
        self.incomplete_download_root = None
        self.stop_event = threading.Event()
        self.monitor_thread = None
        self.set_download_roots()

    def set_download_roots(self):
        normalized_model_root = os.path.normpath(self.model_root)
        normalized_hub_path = os.path.normpath("/models/")
        index = normalized_model_root.find(normalized_hub_path)
        if index > 0:
            self.tmp_download_root = normalized_model_root[:index + len(normalized_hub_path)]

        two_dirs_up = os.path.normpath(os.path.join(normalized_model_root, "..", ".."))
        self.incomplete_download_root = os.path.normpath(os.path.join(two_dirs_up, "blobs"))

    def clean_tmp_files(self):
        for filename in os.listdir(self.tmp_download_root):
            if filename.startswith("tmp"):
                os.remove(os.path.join(self.tmp_download_root, filename))

    def monitor_file_size(self):
        while not self.stop_event.is_set():
            if self.tmp_download_root is not None:
                for filename in os.listdir(self.tmp_download_root):
                    if filename.startswith("tmp"):
                        file_size = os.path.getsize(os.path.join(self.tmp_download_root, filename))
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
):
    progress.emit((1, 100))

    model_root = huggingface_hub.snapshot_download(
        repo_id,
        allow_patterns=allow_patterns[1:],  # all, but largest
        cache_dir=model_root_dir
    )

    progress.emit((1, 100))

    largest_file_url = huggingface_hub.hf_hub_url(repo_id, allow_patterns[0])
    total_file_size = get_file_size(largest_file_url)

    model_download_monitor = HuggingfaceDownloadMonitor(model_root, progress, total_file_size)
    model_download_monitor.start_monitoring()

    huggingface_hub.snapshot_download(
        repo_id,
        allow_patterns=allow_patterns[:1],  # largest
        cache_dir=model_root_dir
    )

    model_download_monitor.stop_monitoring()

    return model_root


def download_faster_whisper_model(
    size: str, local_files_only=False, progress: pyqtSignal(tuple) = None
):
    if size not in faster_whisper.utils._MODELS:
        raise ValueError(
            "Invalid model size '%s', expected one of: %s"
            % (size, ", ".join(faster_whisper.utils._MODELS))
        )

    repo_id = "guillaumekln/faster-whisper-%s" % size

    allow_patterns = [
        "model.bin",  # largest by size first
        "config.json",
        "tokenizer.json",
        "vocabulary.txt",
    ]

    if local_files_only:
        return huggingface_hub.snapshot_download(
            repo_id,
            allow_patterns=allow_patterns,
            local_files_only=True,
            cache_dir=model_root_dir
        )

    return download_from_huggingface(
        repo_id,
        allow_patterns=allow_patterns,
        progress=progress,
    )


class ModelDownloader(QRunnable):
    class Signals(QObject):
        finished = pyqtSignal(str)
        progress = pyqtSignal(tuple)  # (current, total)
        error = pyqtSignal(str)

    def __init__(self, model: TranscriptionModel):
        super().__init__()

        self.signals = self.Signals()
        self.model = model
        self.stopped = False

    def run(self) -> None:
        if self.model.model_type == ModelType.WHISPER_CPP:
            model_name = self.model.whisper_model_size.value
            url = huggingface_hub.hf_hub_url(
                repo_id="ggerganov/whisper.cpp",
                filename=f"ggml-{model_name}.bin",
            )
            file_path = get_whisper_cpp_file_path(size=self.model.whisper_model_size)
            expected_sha256 = WHISPER_CPP_MODELS_SHA256[model_name]
            return self.download_model_to_path(
                url=url, file_path=file_path, expected_sha256=expected_sha256
            )

        if self.model.model_type == ModelType.WHISPER:
            url = whisper._MODELS[self.model.whisper_model_size.value]
            file_path = get_whisper_file_path(size=self.model.whisper_model_size)
            expected_sha256 = url.split("/")[-2]
            return self.download_model_to_path(
                url=url, file_path=file_path, expected_sha256=expected_sha256
            )

        if self.model.model_type == ModelType.FASTER_WHISPER:
            model_path = download_faster_whisper_model(
                size=self.model.whisper_model_size.to_faster_whisper_model_size(),
                progress=self.signals.progress,
            )
            self.signals.finished.emit(model_path)
            return

        if self.model.model_type == ModelType.HUGGING_FACE:
            model_path = download_from_huggingface(
                self.model.hugging_face_model_id,
                allow_patterns=HUGGING_FACE_MODEL_ALLOW_PATTERNS,
                progress=self.signals.progress,
            )
            self.signals.finished.emit(model_path)
            return

        if self.model.model_type == ModelType.OPEN_AI_WHISPER_API:
            self.signals.finished.emit("")
            return

        raise Exception("Invalid model type: " + self.model.model_type.value)

    def download_model_to_path(
        self, url: str, file_path: str, expected_sha256: Optional[str]
    ):
        try:
            downloaded = self.download_model(url, file_path, expected_sha256)
            if downloaded:
                self.signals.finished.emit(file_path)
        except requests.RequestException:
            self.signals.error.emit("A connection error occurred")
            logging.exception("")
        except Exception as exc:
            self.signals.error.emit(str(exc))
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
