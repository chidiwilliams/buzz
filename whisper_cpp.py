import hashlib
import logging
import os
import warnings

import requests
from appdirs import user_cache_dir
from tqdm import tqdm

MODELS_SHA256 = {
    'tiny': 'be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21',
    'small': '60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe',
    'base': '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b'
}


def download_model(name: str):
    """Downloads a Whisper.cpp GGML model to the user cache directory."""

    base_dir = user_cache_dir('Buzz')
    model_path = os.path.join(
        base_dir, f'ggml-model-whisper-{name}.bin')

    if os.path.exists(model_path) and not os.path.isfile(model_path):
        raise RuntimeError(
            f"{model_path} exists and is not a regular file")

    expected_sha256 = MODELS_SHA256[name]

    if os.path.isfile(model_path):
        model_bytes = open(model_path, "rb").read()
        if hashlib.sha256(model_bytes).hexdigest() == expected_sha256:
            return model_path

        logging.debug(
            f"{model_path} exists, but the SHA256 checksum does not match; re-downloading the file")

    url = f'https://ggml.buzz.chidiwilliams.com/ggml-model-whisper-{name}.bin'

    with requests.get(url, stream=True) as source, open(model_path, 'wb') as output:
        source.raise_for_status()

        total_size = int(source.headers.get('Content-Length', 0))
        with tqdm(total=total_size, ncols=80, unit='iB', unit_scale=True, unit_divisor=1024) as loop:
            for chunk in source.iter_content(chunk_size=8192):
                output.write(chunk)
                loop.update(len(chunk))

    model_bytes = open(model_path, "rb").read()
    if hashlib.sha256(model_bytes).hexdigest() != expected_sha256:
        raise RuntimeError(
            "Model has been downloaded but the SHA256 checksum does not match. Please retry loading the model.")

    return model_path
