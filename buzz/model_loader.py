import enum
import hashlib
import logging
import os
import subprocess
import sys
import tempfile
import warnings
from dataclasses import dataclass
from typing import Optional
import shutil

import faster_whisper
import huggingface_hub
import requests
import whisper
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable
from platformdirs import user_cache_dir
from tqdm.auto import tqdm


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


class ModelType(enum.Enum):
    WHISPER = "Whisper"
    WHISPER_CPP = "Whisper.cpp"
    HUGGING_FACE = "Hugging Face"
    FASTER_WHISPER = "Faster Whisper"
    OPEN_AI_WHISPER_API = "OpenAI Whisper API"


@dataclass()
class TranscriptionModel:
    model_type: ModelType = ModelType.WHISPER
    whisper_model_size: Optional[WhisperModelSize] = WhisperModelSize.TINY
    hugging_face_model_id: Optional[str] = None

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
                    self.hugging_face_model_id, local_files_only=True
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


def get_hugging_face_file_url(author: str, repository_name: str, filename: str):
    return f"https://huggingface.co/{author}/{repository_name}/resolve/bf8b606c2fcd9173605cdf6bd2ac8a75a8141b6c/{filename}"


def get_whisper_cpp_file_path(size: WhisperModelSize) -> str:
    root_dir = user_cache_dir("Buzz")
    return os.path.join(root_dir, f"ggml-model-whisper-{size.value}.bin")


def get_whisper_file_path(size: WhisperModelSize) -> str:
    root_dir = os.getenv(
        "XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    )
    url = whisper._MODELS[size.value]
    return os.path.join(root_dir, os.path.basename(url))


def download_faster_whisper_model(
    size: str, local_files_only=False, tqdm_class: Optional[tqdm] = None
):
    if size not in faster_whisper.utils._MODELS:
        raise ValueError(
            "Invalid model size '%s', expected one of: %s"
            % (size, ", ".join(faster_whisper.utils._MODELS))
        )

    repo_id = "guillaumekln/faster-whisper-%s" % size

    allow_patterns = [
        "config.json",
        "model.bin",
        "tokenizer.json",
        "vocabulary.txt",
    ]

    return huggingface_hub.snapshot_download(
        repo_id,
        allow_patterns=allow_patterns,
        local_files_only=local_files_only,
        tqdm_class=tqdm_class,
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
            url = get_hugging_face_file_url(
                author="ggerganov",
                repository_name="whisper.cpp",
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

        progress = self.signals.progress

        # gross abuse of power...
        class _tqdm(tqdm):
            def update(self, n: float | None = ...) -> bool | None:
                progress.emit((n, self.total))
                return super().update(n)

            def close(self):
                progress.emit((self.n, self.total))
                return super().close()

        if self.model.model_type == ModelType.FASTER_WHISPER:
            model_path = download_faster_whisper_model(
                size=self.model.whisper_model_size.to_faster_whisper_model_size(),
                tqdm_class=_tqdm,
            )
            self.signals.finished.emit(model_path)
            return

        if self.model.model_type == ModelType.HUGGING_FACE:
            model_path = huggingface_hub.snapshot_download(
                self.model.hugging_face_model_id, tqdm_class=_tqdm
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
