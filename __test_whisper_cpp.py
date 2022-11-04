import faulthandler
import multiprocessing

from whispr import ModelLoader, Task, WhisperCpp, whisper_cpp_params

faulthandler.enable()

if __name__ == "__main__":
    # Fixes opening new window when app has been frozen on Windows:
    # https://stackoverflow.com/a/33979091
    multiprocessing.freeze_support()

    model_loader = ModelLoader('tiny', True)
    model_path = model_loader.get_model_path()

    whispercpp = WhisperCpp(model_path)
    params = whisper_cpp_params(
        language='fr', task=Task.TRANSCRIBE, print_realtime=True, print_progress=True)
    result = whispercpp.transcribe('./testdata/whisper-french.mp3', params)

    print(result)
