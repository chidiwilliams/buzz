import faulthandler
import multiprocessing
import os

from appdirs import user_cache_dir

from whisper_cpp import String, whisper_init

faulthandler.enable()

if __name__ == "__main__":
    # Fixes opening new window when app has been frozen on Windows:
    # https://stackoverflow.com/a/33979091
    multiprocessing.freeze_support()

    base_dir = user_cache_dir('Buzz')
    os.makedirs(base_dir, exist_ok=True)

    model_path = os.path.join(base_dir, 'ggml-model-whisper-tiny.bin')
    ctx = whisper_init(String(model_path.encode('utf-8')))

    print(ctx)
