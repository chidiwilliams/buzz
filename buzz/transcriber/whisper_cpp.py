import ctypes
import logging
from typing import Union, Any, List

import numpy as np

from buzz import whisper_audio
from buzz.model_loader import LOADED_WHISPER_CPP_BINARY
from buzz.transcriber.transcriber import Segment, Task

if LOADED_WHISPER_CPP_BINARY:
    from buzz import whisper_cpp


class WhisperCpp:
    def __init__(self, model: str) -> None:
        self.ctx = whisper_cpp.whisper_init_from_file(model.encode())

    def transcribe(self, audio: Union[np.ndarray, str], params: Any):
        if isinstance(audio, str):
            audio = whisper_audio.load_audio(audio)

        logging.debug("Loaded audio with length = %s", len(audio))

        whisper_cpp_audio = audio.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        result = whisper_cpp.whisper_full(
            self.ctx, params, whisper_cpp_audio, len(audio)
        )
        if result != 0:
            raise Exception(f"Error from whisper.cpp: {result}")

        segments: List[Segment] = []

        n_segments = whisper_cpp.whisper_full_n_segments((self.ctx))
        for i in range(n_segments):
            txt = whisper_cpp.whisper_full_get_segment_text((self.ctx), i)
            t0 = whisper_cpp.whisper_full_get_segment_t0((self.ctx), i)
            t1 = whisper_cpp.whisper_full_get_segment_t1((self.ctx), i)

            segments.append(
                Segment(
                    start=t0 * 10,  # centisecond to ms
                    end=t1 * 10,  # centisecond to ms
                    text=txt.decode("utf-8"),
                )
            )

        return {
            "segments": segments,
            "text": "".join([segment.text for segment in segments]),
        }

    def __del__(self):
        whisper_cpp.whisper_free(self.ctx)


def whisper_cpp_params(
    language: str,
    task: Task,
    word_level_timings: bool,
    print_realtime=False,
    print_progress=False,
):
    params = whisper_cpp.whisper_full_default_params(
        whisper_cpp.WHISPER_SAMPLING_GREEDY
    )
    params.print_realtime = print_realtime
    params.print_progress = print_progress
    params.language = whisper_cpp.String(language.encode())
    params.translate = task == Task.TRANSLATE
    params.max_len = ctypes.c_int(1)
    params.max_len = 1 if word_level_timings else 0
    params.token_timestamps = word_level_timings
    return params
