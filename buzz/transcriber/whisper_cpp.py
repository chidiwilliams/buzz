import platform
import os
import ctypes
import logging
from typing import Union, Any, List

import numpy as np

from buzz import whisper_audio
from buzz.model_loader import LOADED_WHISPER_CPP_BINARY
from buzz.transcriber.transcriber import Segment, Task, TranscriptionOptions

if LOADED_WHISPER_CPP_BINARY:
    from buzz import whisper_cpp


IS_COREML_SUPPORTED = False
if platform.system() == "Darwin" and platform.machine() == "arm64":
    try:
        from buzz import whisper_cpp_coreml  # noqa: F401

        IS_COREML_SUPPORTED = True
    except ImportError:
        logging.exception("")


class WhisperCpp:
    def __init__(self, model: str) -> None:

        self.is_coreml_supported = IS_COREML_SUPPORTED

        if self.is_coreml_supported:
            coreml_model = model.replace(".bin", "-encoder.mlmodelc")
            if not os.path.exists(coreml_model):
                self.is_coreml_supported = False

        logging.debug(f"WhisperCpp model {model}, (Core ML: {self.is_coreml_supported})")

        self.instance = self.get_instance()
        self.ctx = self.instance.init_from_file(model)
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
        self.segments = []

        if isinstance(audio, str):
            audio = whisper_audio.load_audio(audio)

        logging.debug("Loaded audio with length = %s", len(audio))

        whisper_cpp_audio = audio.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        result = self.instance.full(
            self.ctx, params, whisper_cpp_audio, len(audio)
        )
        if result != 0:
            raise Exception(f"Error from whisper.cpp: {result}")

        n_segments = self.instance.full_n_segments(self.ctx)

        if params.token_timestamps:
            # Will process word timestamps
            txt_buffer = b''
            txt_start = 0
            txt_end = 0

            for i in range(n_segments):
                txt = self.instance.full_get_segment_text(self.ctx, i)
                start = self.instance.full_get_segment_t0(self.ctx, i)
                end = self.instance.full_get_segment_t1(self.ctx, i)

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
                txt = self.instance.full_get_segment_text(self.ctx, i)
                start = self.instance.full_get_segment_t0(self.ctx, i)
                end = self.instance.full_get_segment_t1(self.ctx, i)

                self.append_segment(txt, start, end)

        return {
            "segments": self.segments,
            "text": "".join([segment.text for segment in self.segments]),
        }

    def get_instance(self):
        if self.is_coreml_supported:
            return WhisperCppCoreML()
        return WhisperCppCpu()

    def get_params(
        self,
        transcription_options: TranscriptionOptions,
        print_realtime=False,
        print_progress=False,
    ):
        params = self.instance.full_default_params(whisper_cpp.WHISPER_SAMPLING_GREEDY)
        params.n_threads = int(os.getenv("BUZZ_WHISPERCPP_N_THREADS", 4))
        params.print_realtime = print_realtime
        params.print_progress = print_progress
        params.language = self.instance.get_string((transcription_options.language or "en"))
        params.translate = transcription_options.task == Task.TRANSLATE
        params.max_len = ctypes.c_int(1)
        params.max_len = 1 if transcription_options.word_level_timings else 0
        params.token_timestamps = transcription_options.word_level_timings
        params.initial_prompt = self.instance.get_string(transcription_options.initial_prompt)
        return params

    def __del__(self):
        if self.instance and self.ctx:
            self.instance.free(self.ctx)


class WhisperCppInterface:
    def full_default_params(self, sampling: int):
        raise NotImplementedError

    def get_string(self, string: str):
        raise NotImplementedError

    def get_encoder_begin_callback(self, callback):
        raise NotImplementedError

    def get_new_segment_callback(self, callback):
        raise NotImplementedError

    def init_from_file(self, model: str):
        raise NotImplementedError

    def full(self, ctx, params, audio, length):
        raise NotImplementedError

    def full_n_segments(self, ctx):
        raise NotImplementedError

    def full_get_segment_text(self, ctx, i):
        raise NotImplementedError

    def full_get_segment_t0(self, ctx, i):
        raise NotImplementedError

    def full_get_segment_t1(self, ctx, i):
        raise NotImplementedError

    def free(self, ctx):
        raise NotImplementedError


class WhisperCppCpu(WhisperCppInterface):
    def full_default_params(self, sampling: int):
        return whisper_cpp.whisper_full_default_params(sampling)

    def get_string(self, string: str):
        return whisper_cpp.String(string.encode())

    def get_encoder_begin_callback(self, callback):
        return whisper_cpp.whisper_encoder_begin_callback(callback)

    def get_new_segment_callback(self, callback):
        return whisper_cpp.whisper_new_segment_callback(callback)

    def init_from_file(self, model: str):
        return whisper_cpp.whisper_init_from_file(model.encode())

    def full(self, ctx, params, audio, length):
        return whisper_cpp.whisper_full(ctx, params, audio, length)

    def full_n_segments(self, ctx):
        return whisper_cpp.whisper_full_n_segments(ctx)

    def full_get_segment_text(self, ctx, i):
        return whisper_cpp.whisper_full_get_segment_text(ctx, i)

    def full_get_segment_t0(self, ctx, i):
        return whisper_cpp.whisper_full_get_segment_t0(ctx, i)

    def full_get_segment_t1(self, ctx, i):
        return whisper_cpp.whisper_full_get_segment_t1(ctx, i)

    def free(self, ctx):
        if ctx and whisper_cpp is not None:
            return whisper_cpp.whisper_free(ctx)


class WhisperCppCoreML(WhisperCppInterface):
    def full_default_params(self, sampling: int):
        return whisper_cpp_coreml.whisper_full_default_params(sampling)

    def get_string(self, string: str):
        return whisper_cpp_coreml.String(string.encode())

    def get_encoder_begin_callback(self, callback):
        return whisper_cpp_coreml.whisper_encoder_begin_callback(callback)

    def get_new_segment_callback(self, callback):
        return whisper_cpp_coreml.whisper_new_segment_callback(callback)

    def init_from_file(self, model: str):
        return whisper_cpp_coreml.whisper_init_from_file(model.encode())

    def full(self, ctx, params, audio, length):
        return whisper_cpp_coreml.whisper_full(ctx, params, audio, length)

    def full_n_segments(self, ctx):
        return whisper_cpp_coreml.whisper_full_n_segments(ctx)

    def full_get_segment_text(self, ctx, i):
        return whisper_cpp_coreml.whisper_full_get_segment_text(ctx, i)

    def full_get_segment_t0(self, ctx, i):
        return whisper_cpp_coreml.whisper_full_get_segment_t0(ctx, i)

    def full_get_segment_t1(self, ctx, i):
        return whisper_cpp_coreml.whisper_full_get_segment_t1(ctx, i)

    def free(self, ctx):
        return whisper_cpp_coreml.whisper_free(ctx)
