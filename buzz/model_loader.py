import hashlib
import logging
import os
import warnings

import requests
import whisper
from platformdirs import user_cache_dir
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

MODELS_SHA256 = {
    'tiny': 'be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21',
    'base': '60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe',
    'small': '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b',
    'medium': '6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208',
    'large': '9a423fe4d40c82774b6af34115b8b935f34152246eb19e80e376071d3f999487'
}


class Signals(QObject):
    progress = pyqtSignal(tuple)  # (current, total)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)


class ModelLoader(QRunnable):

    signals: Signals
    stopped = False

    def __init__(self, name: str, use_whisper_cpp=False) -> None:
        super(ModelLoader, self).__init__()
        self.name = name
        self.use_whisper_cpp = use_whisper_cpp
        self.signals = Signals()

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
                    self.signals.completed.emit(model_path)
                    return
                else:
                    warnings.warn(
                        f"{model_path} exists, but the SHA256 checksum does not match; re-downloading the file")

            # Downloads the model using the requests module instead of urllib to
            # use the certs from certifi when the app is running in frozen mode
            with requests.get(url, stream=True, timeout=15) as source, open(model_path, 'wb') as output:
                source.raise_for_status()
                total_size = int(source.headers.get('Content-Length', 0))
                current = 0
                self.signals.progress.emit((0, total_size))
                for chunk in source.iter_content(chunk_size=8192):
                    if self.stopped:
                        return
                    output.write(chunk)
                    current += len(chunk)
                    self.signals.progress.emit((current, total_size))

            model_bytes = open(model_path, "rb").read()
            if hashlib.sha256(model_bytes).hexdigest() != expected_sha256:
                raise RuntimeError(
                    "Model has been downloaded but the SHA256 checksum does not match. Please retry loading the model.")

            self.signals.completed.emit(model_path)
        except RuntimeError as exc:
            self.signals.error.emit(str(exc))
            logging.exception('')
        except requests.RequestException:
            self.signals.error.emit('A connection error occurred')
            logging.exception('')
        except Exception:
            self.signals.error.emit('An unknown error occurred')
            logging.exception('')

    def stop(self):
        self.stopped = True
