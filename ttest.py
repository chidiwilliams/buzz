import ctypes
import whisper

import whisper_cpp
from whispr import download_whisper_cpp_model

model_path = download_whisper_cpp_model('tiny')

ctx = whisper_cpp.whisper_init(model_path.encode('utf-8'))
audio = whisper.audio.load_audio('./testdata/whisper-french.mp3')

params = whisper_cpp.whisper_full_default_params(0)
params.print_realtime = True
params.print_progress = True
params.language = whisper_cpp.String('fr'.encode('utf-8'))
params.translate = False

result = whisper_cpp.whisper_full(
    ctx, params, audio.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), len(audio))

print(result)

whisper_cpp.whisper_free(ctx)
