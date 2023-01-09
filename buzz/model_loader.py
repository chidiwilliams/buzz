import enum
import hashlib
import logging
import os
import warnings
from dataclasses import dataclass
from typing import Optional

import requests
import whisper
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from platformdirs import user_cache_dir

from buzz import transformers_whisper


class WhisperModelSize(enum.Enum):
    TINY = 'tiny'
    BASE = 'base'
    SMALL = 'small'
    MEDIUM = 'medium'
    LARGE = 'large'


class ModelType(enum.Enum):
    WHISPER = 'Whisper'
    WHISPER_CPP = 'Whisper.cpp'
    HUGGING_FACE = 'Hugging Face'


@dataclass()
class TranscriptionModel:
    model_type: ModelType = ModelType.WHISPER
    whisper_model_size: Optional[WhisperModelSize] = WhisperModelSize.TINY
    hugging_face_model_id: Optional[str] = None


WHISPER_CPP_MODELS_SHA256 = {
    'tiny': 'be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21',
    'base': '60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe',
    'small': '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b',
    'medium': '6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208',
    'large': '9a423fe4d40c82774b6af34115b8b935f34152246eb19e80e376071d3f999487'
}


def get_hugging_face_dataset_file_url(author: str, repository_name: str, filename: str):
    return f'https://huggingface.co/datasets/{author}/{repository_name}/resolve/main/{filename}'


class ModelLoader(QObject):
    progress = pyqtSignal(tuple)  # (current, total)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    stopped = False

    def __init__(self, model: TranscriptionModel, parent: Optional['QObject'] = None) -> None:
        super().__init__(parent)
        self.model_type = model.model_type
        self.whisper_model_size = model.whisper_model_size
        self.hugging_face_model_id = model.hugging_face_model_id

    @pyqtSlot()
    def run(self):
        if self.model_type == ModelType.WHISPER_CPP:
            root_dir = user_cache_dir('Buzz')
            model_name = self.whisper_model_size.value
            url = get_hugging_face_dataset_file_url(author='ggerganov', repository_name='whisper.cpp',
                                                    filename=f'ggml-{model_name}.bin')
            file_path = os.path.join(root_dir, f'ggml-model-whisper-{model_name}.bin')
            expected_sha256 = WHISPER_CPP_MODELS_SHA256[model_name]
            self.download_model(url, file_path, expected_sha256)

        elif self.model_type == ModelType.WHISPER:
            root_dir = os.getenv(
                "XDG_CACHE_HOME",
                os.path.join(os.path.expanduser("~"), ".cache", "whisper")
            )
            model_name = self.whisper_model_size.value
            url = whisper._MODELS[model_name]
            file_path = os.path.join(root_dir, os.path.basename(url))
            expected_sha256 = url.split('/')[-2]
            self.download_model(url, file_path, expected_sha256)

        else:  # ModelType.HUGGING_FACE:
            self.progress.emit((0, 100))

            try:
                # Loads the model from cache or download if not in cache
                transformers_whisper.load_model(self.hugging_face_model_id)
            except (FileNotFoundError, EnvironmentError) as exception:
                self.error.emit(f'{exception}')
                return

            self.progress.emit((100, 100))
            file_path = self.hugging_face_model_id

        self.finished.emit(file_path)

    def download_model(self, url: str, file_path: str, expected_sha256: Optional[str]):
        try:
            logging.debug(f'Downloading model from {url} to {file_path}')

            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            if os.path.exists(file_path) and not os.path.isfile(file_path):
                raise RuntimeError(
                    f"{file_path} exists and is not a regular file")

            if os.path.isfile(file_path):
                if expected_sha256 is None:
                    return file_path

                model_bytes = open(file_path, "rb").read()
                model_sha256 = hashlib.sha256(model_bytes).hexdigest()
                if model_sha256 == expected_sha256:
                    return file_path
                else:
                    warnings.warn(
                        f"{file_path} exists, but the SHA256 checksum does not match; re-downloading the file")

            # Downloads the model using the requests module instead of urllib to
            # use the certs from certifi when the app is running in frozen mode
            with requests.get(url, stream=True, timeout=15) as source, open(file_path, 'wb') as output:
                source.raise_for_status()
                total_size = float(source.headers.get('Content-Length', 0))
                current = 0.0
                self.progress.emit((current, total_size))
                for chunk in source.iter_content(chunk_size=8192):
                    if self.stopped:
                        return
                    output.write(chunk)
                    current += len(chunk)
                    self.progress.emit((current, total_size))

            if expected_sha256 is not None:
                model_bytes = open(file_path, "rb").read()
                if hashlib.sha256(model_bytes).hexdigest() != expected_sha256:
                    raise RuntimeError(
                        "Model has been downloaded but the SHA256 checksum does not match. Please retry loading the "
                        "model.")

            logging.debug('Downloaded model')

            return file_path
        except RuntimeError as exc:
            self.error.emit(str(exc))
            logging.exception('')
        except requests.RequestException:
            self.error.emit('A connection error occurred')
            logging.exception('')
        except Exception:
            self.error.emit('An unknown error occurred')
            logging.exception('')

    def stop(self):
        self.stopped = True
