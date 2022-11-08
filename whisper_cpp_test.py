import hashlib
import logging
import os
import sys
from subprocess import PIPE, Popen

import ffmpeg
import requests
import whisper
from platformdirs import user_cache_dir
from tqdm import tqdm

INPUT_FILE = 'testdata/whisper-french.mp3'
OUTPUT_FILE = 'testdata/whisper-french.wav'

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


def reader(pipe, queue):
    try:
        with pipe:
            for line in iter(pipe.readline, b''):
                queue.put((pipe, line))
    finally:
        queue.put(None)


model_path = download_whisper_cpp_model('tiny')


ffmpeg.input(INPUT_FILE).output(
    OUTPUT_FILE,
    acodec="pcm_s16le",
    ac=1, ar=whisper.audio.SAMPLE_RATE,
).overwrite_output().run()

# Adds the current directory to the PATH, so the ffmpeg binary get picked up:
# https://stackoverflow.com/a/44352931/9830227
app_dir = getattr(sys, '_MEIPASS', os.path.dirname(
    os.path.abspath(__file__)))
os.environ["PATH"] += os.pathsep + app_dir

process = Popen([
    'whisper_cpp',
    '-f', OUTPUT_FILE,
    '-m', model_path],
    stdout=PIPE,
    stderr=PIPE, bufsize=1)

process.wait()

print('processs done')
print(process.stderr.read().decode())
print(process.stdout.read().decode())
