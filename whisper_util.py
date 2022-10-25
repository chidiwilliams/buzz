import ctypes
import enum
import hashlib
import multiprocessing
import os
import pathlib
import warnings
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Union

import numpy as np
import requests
import whisper
from tqdm import tqdm
from whisper import Whisper

from fd import capture_fd, read_pipe_str
from whisper_cpp import download_model


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


class WhisperFullParams(ctypes.Structure):
    _fields_ = [
        ("strategy",             ctypes.c_int),
        ("n_threads",            ctypes.c_int),
        ("offset_ms",            ctypes.c_int),
        ("translate",            ctypes.c_bool),
        ("no_context",           ctypes.c_bool),
        ("print_special_tokens", ctypes.c_bool),
        ("print_progress",       ctypes.c_bool),
        ("print_realtime",       ctypes.c_bool),
        ("print_timestamps",     ctypes.c_bool),
        ("language",             ctypes.c_char_p),
        ("greedy",               ctypes.c_int * 1),
    ]


whisper_cpp = ctypes.CDLL(
    str(pathlib.Path().absolute() / "libwhisper.so"), winmode=1)

whisper_cpp.whisper_init.restype = ctypes.c_void_p
whisper_cpp.whisper_full_default_params.restype = WhisperFullParams
whisper_cpp.whisper_full_get_segment_text.restype = ctypes.c_char_p


def whisper_cpp_progress(lines: str):
    """Extracts the progress of a whisper.cpp transcription.

    The log lines have the following format:
        whisper_full: progress = 20%\n
    """

    # Example log line: "whisper_full: progress = 20%"
    progress_lines = list(filter(lambda line: line.startswith(
        'whisper_full: progress'), lines.split('\n')))
    if len(progress_lines) == 0:
        raise Exception('No lines match whisper.cpp progress format')
    last_word = progress_lines[-1].split(' ')[-1]
    return min(int(last_word[:-1]), 100)


def whisper_cpp_params(language: str, task: Task, print_realtime=False, print_progress=False):
    params = whisper_cpp.whisper_full_default_params(0)
    params.print_realtime = print_realtime
    params.print_progress = print_progress
    params.language = language.encode('utf-8')
    params.translate = task == Task.TRANSLATE
    return params


class WhisperCpp:
    def __init__(self, model: str) -> None:
        self.ctx = whisper_cpp.whisper_init(model.encode('utf-8'))

    def transcribe(self, audio: Union[np.ndarray, str], params: Any):
        if isinstance(audio, str):
            audio = whisper.audio.load_audio(audio)

        result = whisper_cpp.whisper_full(ctypes.c_void_p(
            self.ctx), params, audio.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), len(audio))
        if result != 0:
            raise Exception(f'Error from whisper.cpp: {result}')

        segments: List[Segment] = []

        n_segments = whisper_cpp.whisper_full_n_segments(
            ctypes.c_void_p(self.ctx))
        for i in range(n_segments):
            txt = whisper_cpp.whisper_full_get_segment_text(
                ctypes.c_void_p(self.ctx), i)
            t0 = whisper_cpp.whisper_full_get_segment_t0(
                ctypes.c_void_p(self.ctx), i)
            t1 = whisper_cpp.whisper_full_get_segment_t1(
                ctypes.c_void_p(self.ctx), i)

            segments.append(
                Segment(start=t0*10,  # centisecond to ms
                        end=t1*10,  # centisecond to ms
                        text=txt.decode('utf-8')))

        return {
            'segments': segments,
            'text': ''.join([segment.text for segment in segments])}

    def __del__(self):
        whisper_cpp.whisper_free(ctypes.c_void_p(self.ctx))


class ModelLoader:
    stopped = False
    process: Optional[multiprocessing.Process] = None

    def __init__(self, name: str, use_whisper_cpp=False,
                 on_download_model_chunk: Callable[[int, int], None] = lambda *_: None) -> None:
        self.name = name
        self.on_download_model_chunk = on_download_model_chunk
        self.use_whisper_cpp = use_whisper_cpp

    def load(self) -> Union[Whisper, WhisperCpp]:
        queue = multiprocessing.Queue()

        # Fixes an issue with the pickling of a torch model from another process
        if self.use_whisper_cpp is False:
            os.environ["no_proxy"] = '*'

        with capture_fd(2) as (prev_stderr, stderr):
            self.process = multiprocessing.Process(
                target=self.load_whisper_cpp_model if self.use_whisper_cpp else self.load_whisper_model, args=(queue, self.name))
            self.process.start()

            while self.process.is_alive():
                if self.stopped:
                    self.process.kill()
                    raise Stopped

                next_stderr = read_pipe_str(stderr)
                if len(next_stderr) > 0:
                    os.write(prev_stderr, next_stderr.encode('utf-8'))
                    # tqdm progress line looks like: " 54%|█████       |"
                    percent_progress = next_stderr.split(
                        '|')[0].strip().strip('%')
                    try:
                        self.on_download_model_chunk(
                            int(percent_progress), 100)
                    except ValueError:
                        continue

        self.process.join()
        return WhisperCpp(queue.get()) if self.use_whisper_cpp else queue.get()

    def load_whisper_cpp_model(self, queue: multiprocessing.Queue, name: str):
        model_path = download_model(name)
        queue.put(model_path)

    def load_whisper_model(self, queue: multiprocessing.Queue, name: str):
        download_root = os.getenv(
            "XDG_CACHE_HOME",
            os.path.join(os.path.expanduser("~"), ".cache", "whisper")
        )
        path = _download(whisper._MODELS[name], download_root)
        model = whisper.load_model(path)
        queue.put(model)

    def stop(self):
        self.stopped = True

        if self.process is not None:
            self.process.join()

    def is_stopped(self):
        return self.stopped


def _download(url: str, root: str):
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
