import ctypes
import enum
import hashlib
import logging
import multiprocessing
import os
import warnings
from dataclasses import dataclass
from multiprocessing.connection import Connection
from queue import Empty
from threading import Thread
from typing import Any, Callable, List, Union

import numpy as np
import requests
import whisper
from appdirs import user_cache_dir
from tqdm import tqdm
from whisper import Whisper

from conn import pipe_stderr
from whisper_cpp import (String, whisper_free, whisper_full,
                         whisper_full_default_params,
                         whisper_full_get_segment_t0,
                         whisper_full_get_segment_t1,
                         whisper_full_get_segment_text,
                         whisper_full_n_segments, whisper_init)


class Stopped(Exception):
    pass


@dataclass
class Segment:
    start: float
    end: float
    text: str


class Task(enum.Enum):
    TRANSLATE = "translate"
    TRANSCRIBE = "transcribe"


def whisper_cpp_params(language: str, task: Task, print_realtime=False, print_progress=False):
    params = whisper_full_default_params(0)
    params.print_realtime = print_realtime
    params.print_progress = print_progress
    params.language = String(language.encode('utf-8'))
    params.translate = task == Task.TRANSLATE
    return params


class WhisperCpp:
    def __init__(self, model: str) -> None:
        self.ctx = whisper_init(String(model.encode('utf-8')))

    def transcribe(self, audio: Union[np.ndarray, str], params: Any):
        if isinstance(audio, str):
            audio = whisper.audio.load_audio(audio)

        logging.debug('Loaded audio with length = %s', len(audio))

        whisper_cpp_audio = audio.ctypes.data_as(
            ctypes.POINTER(ctypes.c_float))
        result = whisper_full(
            self.ctx, params, whisper_cpp_audio, len(audio))
        if result != 0:
            raise Exception(f'Error from whisper.cpp: {result}')

        segments: List[Segment] = []

        n_segments = whisper_full_n_segments(
            (self.ctx))
        for i in range(n_segments):
            txt = whisper_full_get_segment_text(self.ctx, i)
            t0 = whisper_full_get_segment_t0(self.ctx, i)
            t1 = whisper_full_get_segment_t1(self.ctx, i)

            segments.append(
                Segment(start=t0*10,  # centisecond to ms
                        end=t1*10,  # centisecond to ms
                        text=txt.decode('utf-8')))

        return {
            'segments': segments,
            'text': ''.join([segment.text for segment in segments])}

    def __del__(self):
        whisper_free(self.ctx)


# TODO: should this instead subclass Process?
class ModelLoader:
    process: multiprocessing.Process
    model_path_queue: multiprocessing.Queue

    def __init__(self, name: str, use_whisper_cpp=False) -> None:
        self.name = name
        self.use_whisper_cpp = use_whisper_cpp

        self.recv_pipe, self.send_pipe = multiprocessing.Pipe(duplex=False)
        self.model_path_queue = multiprocessing.Queue()
        self.process = multiprocessing.Process(
            target=self.load_whisper_cpp_model if self.use_whisper_cpp else self.load_whisper_model,
            args=(self.send_pipe, self.model_path_queue, self.name))

    def get_model_path(self,  on_download_model_chunk: Callable[[int, int], None] = lambda *_: None) -> str:
        # Fixes an issue with the pickling of a torch model from another process
        os.environ["no_proxy"] = '*'

        on_download_model_chunk(0, 100)

        self.process.start()

        thread = Thread(target=read_progress, args=(
            self.recv_pipe, self.use_whisper_cpp, on_download_model_chunk))
        thread.start()

        self.process.join()

        self.recv_pipe.close()
        self.send_pipe.close()

        on_download_model_chunk(100, 100)
        try:
            return self.model_path_queue.get(block=False)
        except Empty as exc:
            raise Stopped from exc

    def load(self, on_download_model_chunk: Callable[[int, int], None] = lambda *_: None) -> Union[Whisper, WhisperCpp]:
        logging.debug(
            'Loading model = %s, whisper.cpp = %s', self.name, self.use_whisper_cpp)

        model_path = self.get_model_path(on_download_model_chunk)

        logging.debug('Loading model from path = %s', model_path)
        return WhisperCpp(model_path) if self.use_whisper_cpp else whisper.load_model(model_path)

    def load_whisper_cpp_model(self, stderr_conn: Connection, queue: multiprocessing.Queue, name: str):
        path = download_whisper_cpp_model(name)
        queue.put(path)

    def load_whisper_model(self, stderr_conn: Connection, queue: multiprocessing.Queue, name: str):
        with pipe_stderr(stderr_conn):
            download_root = os.getenv(
                "XDG_CACHE_HOME",
                os.path.join(os.path.expanduser("~"), ".cache", "whisper")
            )
            path = download_whisper_model(whisper._MODELS[name], download_root)
            queue.put(path)

    def stop(self):
        if self.process.is_alive():
            self.process.terminate()

    def is_alive(self):
        return self.process.is_alive()


def download_whisper_model(url: str, root: str):
    """See whisper._download"""
    os.makedirs(root, exist_ok=True)

    expected_sha256 = url.split("/")[-2]
    download_target = os.path.join(root, os.path.basename(url))

    if os.path.exists(download_target) and not os.path.isfile(download_target):
        raise RuntimeError(
            f"{download_target} exists and is not a regular file")

    if os.path.isfile(download_target):
        model_bytes = open(download_target, "rb").read()
        if hashlib.sha256(model_bytes).hexdigest() == expected_sha256:
            return download_target
        else:
            warnings.warn(
                f"{download_target} exists, but the SHA256 checksum does not match; re-downloading the file")

    # Downloads the model using the requests module instead of urllib to
    # use the certs from certifi when the app is running in frozen mode
    with requests.get(url, stream=True, timeout=15) as source, open(download_target, 'wb') as output:
        source.raise_for_status()
        total_size = int(source.headers.get('Content-Length', 0))
        with tqdm(total=total_size, ncols=80, unit='iB', unit_scale=True, unit_divisor=1024) as loop:
            for chunk in source.iter_content(chunk_size=8192):
                output.write(chunk)
                loop.update(len(chunk))

    model_bytes = open(download_target, "rb").read()
    if hashlib.sha256(model_bytes).hexdigest() != expected_sha256:
        raise RuntimeError(
            "Model has been downloaded but the SHA256 checksum does not not match. Please retry loading the model.")

    return download_target


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


# tqdm progress line looks like: " 54%|█████       |"
def tqdm_progress(line: str):
    percent_progress = line.split('|')[0].strip().strip('%')
    return int(percent_progress)


def whisper_cpp_progress(lines: str):
    """Extracts the progress of a whisper.cpp transcription.

    The log lines have the following format:
        whisper_full: progress = 20%\n
    """

    # Example log line: "whisper_full: progress = 20%"
    progress_lines = list(filter(lambda line: line.startswith(
        'whisper_full: progress'), lines.split('\n')))
    if len(progress_lines) == 0:
        raise ValueError('No lines match whisper.cpp progress format')
    last_word = progress_lines[-1].split(' ')[-1]
    return min(int(last_word[:-1]), 100)


def read_progress(
        pipe: Connection, use_whisper_cpp: bool,
        progress_callback: Callable[[int, int], None]):
    while True:
        try:
            recv = pipe.recv().strip()
            if recv:
                if use_whisper_cpp:
                    progress = whisper_cpp_progress(recv)
                else:
                    progress = tqdm_progress(recv)
                progress_callback(progress, 100)
        except ValueError:
            pass
        except EOFError:
            break
