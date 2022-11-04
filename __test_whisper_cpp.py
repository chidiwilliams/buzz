import faulthandler
import multiprocessing

from whisper_cpp import String, whisper_free, whisper_init
from whispr import download_whisper_cpp_model

faulthandler.enable()

if __name__ == "__main__":
    # Fixes opening new window when app has been frozen on Windows:
    # https://stackoverflow.com/a/33979091
    multiprocessing.freeze_support()

    model_path = download_whisper_cpp_model("tiny")
    ctx = whisper_init(String(model_path.encode('utf-8')))
    print(ctx)
    whisper_free(ctx)
