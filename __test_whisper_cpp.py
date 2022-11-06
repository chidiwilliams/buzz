
import ctypes
import faulthandler
import hashlib
import logging
import os
import pathlib

import requests
import whisper
from appdirs import user_cache_dir
from tqdm import tqdm

faulthandler.enable()


class WhisperFullParams(ctypes.Structure):
    _fields_ = [
        ("strategy",             ctypes.c_int),
        ("n_threads",            ctypes.c_int),
        ("n_max_text_ctx",            ctypes.c_int),
        ("offset_ms",            ctypes.c_int),
        ("translate",            ctypes.c_bool),
        ("no_context",           ctypes.c_bool),
        ("print_special_tokens", ctypes.c_bool),
        ("print_progress",       ctypes.c_bool),
        ("print_realtime",       ctypes.c_bool),
        ("print_timestamps",     ctypes.c_bool),
        ("token_timestamps",     ctypes.c_bool),
        ("thold_pt",     ctypes.c_float),
        ("thold_ptsum",     ctypes.c_float),
        ("max_len",     ctypes.c_int),

        ("language",             ctypes.c_char_p),
        ("greedy",               ctypes.c_int * 1),
        ("beam_search",               ctypes.c_int * 1),
        ("new_segment_callback",               ctypes.c_void_p),
        ("new_segment_callback_user_data",               ctypes.c_void_p),
    ]


whisper_cpp = ctypes.CDLL(
    str(pathlib.Path().absolute() / "libwhisper.dylib"),)

whisper_cpp.whisper_init.restype = ctypes.c_void_p
whisper_cpp.whisper_full_default_params.restype = WhisperFullParams
whisper_cpp.whisper_full_get_segment_text.restype = ctypes.c_char_p

MODELS_SHA256 = {
    'tiny': 'be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21',
    'base': '60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe',
    'small': '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b',
}


def download_whisper_cpp_model(name: str):
    """Downloads a Whisper.cpp GGML model to the user cache directory."""

    base_dir = user_cache_dir('Buzz')
    os.makedirs(base_dir, exist_ok=True)

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
            '%s exists, but the SHA256 checksum does not match; re-downloading the file', model_path)

    url = f'https://ggml.buzz.chidiwilliams.com/ggml-model-whisper-{name}.bin'
    with requests.get(url, stream=True, timeout=15) as source, open(model_path, 'wb') as output:
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


if __name__ == "__main__":
    # Fixes opening new window when app has been frozen on Windows:
    # https://stackoverflow.com/a/33979091
    # multiprocessing.freeze_support()

    model_path = download_whisper_cpp_model("tiny")
    ctx = ctypes.c_void_p(whisper_cpp.whisper_init(
        (model_path.encode('utf-8'))))

    audio = whisper.audio.load_audio('./testdata/whisper-french.mp3')

    params = whisper_cpp.whisper_full_default_params(0)

    whisper_cpp_audio = audio.ctypes.data_as(
        ctypes.POINTER(ctypes.c_float))
    result = whisper_cpp.whisper_full(
        (ctx), params, whisper_cpp_audio, len(audio))
    if result != 0:
        raise Exception(f'Error from whisper.cpp: {result}')

    n_segments = whisper_cpp.whisper_full_n_segments(((ctx)))
    for i in range(n_segments):
        txt = whisper_cpp.whisper_full_get_segment_text(
            (ctx), i)
        t0 = whisper_cpp.whisper_full_get_segment_t0((ctx), i)
        t1 = whisper_cpp.whisper_full_get_segment_t1((ctx), i)

        print(t0, t1, txt.decode('utf-8'))

    whisper_cpp.whisper_free((ctx))
