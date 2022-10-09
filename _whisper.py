

import hashlib
import os
import warnings
from typing import Union

import requests
import whisper


def load_model(name: str):
    """
    Loads a Whisper ASR model.

    This is a patch for whisper.load_model that downloads the models using the requests module
    instead of urllib.request to allow the program get the correct SSL certificates when run from
    a PyInstaller application.
    """
    download_root = os.path.join(
        os.path.expanduser("~"), ".cache", "whisper")

    url = whisper._MODELS[name]
    _download(url=url, root=download_root, in_memory=False)

    download_target = os.path.join(download_root, os.path.basename(url))

    return whisper.load_model(name=download_target, download_root=download_root)


def _download(url: str, root: str, in_memory: bool) -> Union[bytes, str]:
    """ See whisper._download """
    os.makedirs(root, exist_ok=True)

    expected_sha256 = url.split("/")[-2]
    download_target = os.path.join(root, os.path.basename(url))

    if os.path.exists(download_target) and not os.path.isfile(download_target):
        raise RuntimeError(
            f"{download_target} exists and is not a regular file")

    if os.path.isfile(download_target):
        model_bytes = open(download_target, "rb").read()
        if hashlib.sha256(model_bytes).hexdigest() == expected_sha256:
            return model_bytes if in_memory else download_target
        else:
            warnings.warn(
                f"{download_target} exists, but the SHA256 checksum does not match; re-downloading the file")

    with requests.get(url, stream=True) as source, open(download_target, 'wb') as output:
        source.raise_for_status()
        for chunk in source.iter_content(chunk_size=8192):
            output.write(chunk)

    model_bytes = open(download_target, "rb").read()
    if hashlib.sha256(model_bytes).hexdigest() != expected_sha256:
        raise RuntimeError(
            "Model has been downloaded but the SHA256 checksum does not not match. Please retry loading the model.")

    return model_bytes if in_memory else download_target
