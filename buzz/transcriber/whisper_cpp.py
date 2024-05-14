import ctypes
import logging
from typing import Union, Any, List

import numpy as np

from buzz import whisper_audio
from buzz.model_loader import LOADED_WHISPER_CPP_BINARY
from buzz.transcriber.transcriber import Segment, Task, TranscriptionOptions

if LOADED_WHISPER_CPP_BINARY:
    from buzz import whisper_cpp


class WhisperCpp:
    def __init__(self, model: str) -> None:
        self.ctx = whisper_cpp.whisper_init_from_file(model.encode())
        self.segments: List[Segment] = []

    def append_segment(self, txt: bytes, start: int, end: int):
        if txt == b'':
            return True

        # try-catch will guard against multi-byte utf-8 characters
        # https://github.com/ggerganov/whisper.cpp/issues/1798
        try:
            self.segments.append(
                Segment(
                    start=start * 10,  # centisecond to ms
                    end=end * 10,  # centisecond to ms
                    text=txt.decode("utf-8"),
                )
            )

            return True
        except UnicodeDecodeError:
            return False

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

        n_segments = whisper_cpp.whisper_full_n_segments(self.ctx)

        if params.token_timestamps:
            # Will process word timestamps
            txt_buffer = b''
            txt_start = 0
            txt_end = 0

            for i in range(n_segments):
                txt = whisper_cpp.whisper_full_get_segment_text(self.ctx, i)
                start = whisper_cpp.whisper_full_get_segment_t0(self.ctx, i)
                end = whisper_cpp.whisper_full_get_segment_t1(self.ctx, i)

                if txt.startswith(b' ') and self.append_segment(txt_buffer, txt_start, txt_end):
                    txt_buffer = txt
                    txt_start = start
                    txt_end = end
                    continue

                if txt.startswith(b', '):
                    txt_buffer += b','
                    self.append_segment(txt_buffer, txt_start, txt_end)
                    txt_buffer = txt.lstrip(b',')
                    txt_start = start
                    txt_end = end
                    continue

                txt_buffer += txt
                txt_end = end

            # Append the last segment
            self.append_segment(txt_buffer, txt_start, txt_end)

        else:
            for i in range(n_segments):
                txt = whisper_cpp.whisper_full_get_segment_text(self.ctx, i)
                start = whisper_cpp.whisper_full_get_segment_t0(self.ctx, i)
                end = whisper_cpp.whisper_full_get_segment_t1(self.ctx, i)

                self.append_segment(txt, start, end)

        return {
            "segments": self.segments,
            "text": "".join([segment.text for segment in self.segments]),
        }

    def __del__(self):
        whisper_cpp.whisper_free(self.ctx)


def whisper_cpp_params(
    transcription_options: TranscriptionOptions,
    print_realtime=False,
    print_progress=False,
):
    params = whisper_cpp.whisper_full_default_params(
        whisper_cpp.WHISPER_SAMPLING_GREEDY
    )
    params.print_realtime = print_realtime
    params.print_progress = print_progress

    params.language = whisper_cpp.String(
        (transcription_options.language or "en").encode()
    )
    params.translate = transcription_options.task == Task.TRANSLATE
    params.max_len = ctypes.c_int(1)
    params.max_len = 1 if transcription_options.word_level_timings else 0
    params.token_timestamps = transcription_options.word_level_timings
    params.initial_prompt = whisper_cpp.String(
        transcription_options.initial_prompt.encode()
    )
    return params
