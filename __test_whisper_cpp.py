import ctypes
import faulthandler
import multiprocessing

import whisper

from whisper_cpp import (String, whisper_free, whisper_full,
                         whisper_full_default_params,
                         whisper_full_get_segment_t0,
                         whisper_full_get_segment_t1,
                         whisper_full_get_segment_text,
                         whisper_full_n_segments, whisper_init)
from whispr import download_whisper_cpp_model

# faulthandler.enable()

if __name__ == "__main__":
    # Fixes opening new window when app has been frozen on Windows:
    # https://stackoverflow.com/a/33979091
    # multiprocessing.freeze_support()

    model_path = download_whisper_cpp_model("tiny")
    ctx = whisper_init(String(model_path.encode('utf-8')))

    audio = whisper.audio.load_audio('./testdata/whisper-french.mp3')

    params = whisper_full_default_params(0)

    whisper_cpp_audio = audio.ctypes.data_as(
        ctypes.POINTER(ctypes.c_float))
    result = whisper_full(ctx, params, whisper_cpp_audio, len(audio))
    if result != 0:
        raise Exception(f'Error from whisper.cpp: {result}')

    n_segments = whisper_full_n_segments((ctx))
    for i in range(n_segments):
        txt = whisper_full_get_segment_text(ctx, i)
        t0 = whisper_full_get_segment_t0(ctx, i)
        t1 = whisper_full_get_segment_t1(ctx, i)

        print(t0, t1, txt.decode('utf-8'))

    whisper_free(ctx)
