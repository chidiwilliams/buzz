
import ctypes
import faulthandler
import pathlib

import whisper

from whispr import download_whisper_cpp_model

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

if __name__ == "__main__":
    # Fixes opening new window when app has been frozen on Windows:
    # https://stackoverflow.com/a/33979091
    # multiprocessing.freeze_support()

    model_path = download_whisper_cpp_model("tiny")
    ctx = whisper_cpp.whisper_init((model_path.encode('utf-8')))

    audio = whisper.audio.load_audio('./testdata/whisper-french.mp3')

    params = whisper_cpp.whisper_full_default_params(0)

    whisper_cpp_audio = audio.ctypes.data_as(
        ctypes.POINTER(ctypes.c_float))
    result = whisper_cpp.whisper_full(
        ctypes.c_void_p(ctx), params, whisper_cpp_audio, len(audio))
    if result != 0:
        raise Exception(f'Error from whisper.cpp: {result}')

    n_segments = whisper_cpp.whisper_full_n_segments((ctypes.c_void_p(ctx)))
    for i in range(n_segments):
        txt = whisper_cpp.whisper_full_get_segment_text(ctypes.c_void_p(ctx), i)
        t0 = whisper_cpp.whisper_full_get_segment_t0(ctypes.c_void_p(ctx), i)
        t1 = whisper_cpp.whisper_full_get_segment_t1(ctypes.c_void_p(ctx), i)

        print(t0, t1, txt.decode('utf-8'))

    whisper_cpp.whisper_free(ctypes.c_void_p(ctx))
