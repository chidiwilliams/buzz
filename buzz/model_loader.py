import hashlib
import logging
import os
import warnings
from typing import Optional

import requests
import whisper
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from platformdirs import user_cache_dir

from buzz.transcriber import Model

MODELS_SHA256 = {
    'tiny': 'be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21',
    'base': '60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe',
    'small': '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b',
    'medium': '6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208',
    'large': '9a423fe4d40c82774b6af34115b8b935f34152246eb19e80e376071d3f999487'
}


class ModelLoader(QObject):
    progress = pyqtSignal(tuple)  # (current, total)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    stopped = False

    def __init__(self, model: Model, parent: Optional['QObject'] = None) -> None:
        super().__init__(parent)
        self.name = model.model_name()
        self.use_whisper_cpp = model.is_whisper_cpp()

    @pyqtSlot()
    def run(self):
        try:
            if self.use_whisper_cpp:
                root = user_cache_dir('Buzz')
                url = f'https://ggml.buzz.chidiwilliams.com/ggml-model-whisper-{self.name}.bin'
            else:
                root = os.getenv(
                    "XDG_CACHE_HOME",
                    os.path.join(os.path.expanduser("~"), ".cache", "whisper")
                )
                url = whisper._MODELS[self.name]

            os.makedirs(root, exist_ok=True)

            model_path = os.path.join(root, os.path.basename(url))

            if os.path.exists(model_path) and not os.path.isfile(model_path):
                raise RuntimeError(
                    f"{model_path} exists and is not a regular file")

            expected_sha256 = MODELS_SHA256[self.name] if self.use_whisper_cpp else url.split(
                "/")[-2]
            if os.path.isfile(model_path):
                model_bytes = open(model_path, "rb").read()
                model_sha256 = hashlib.sha256(model_bytes).hexdigest()
                if model_sha256 == expected_sha256:
                    self.finished.emit(model_path)
                    return
                else:
                    warnings.warn(
                        f"{model_path} exists, but the SHA256 checksum does not match; re-downloading the file")

            # Downloads the model using the requests module instead of urllib to
            # use the certs from certifi when the app is running in frozen mode
            with requests.get(url, stream=True, timeout=15) as source, open(model_path, 'wb') as output:
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

            model_bytes = open(model_path, "rb").read()
            if hashlib.sha256(model_bytes).hexdigest() != expected_sha256:
                raise RuntimeError(
                    "Model has been downloaded but the SHA256 checksum does not match. Please retry loading the model.")

            self.finished.emit(model_path)
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
