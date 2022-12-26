from buzz.model_loader import ModelLoader
from buzz.transcriber import TranscriptionOptions


def get_model_path(transcription_options: TranscriptionOptions) -> str:
    model_loader = ModelLoader(transcription_options=transcription_options)
    model_path = ''

    def on_load_model(path: str):
        nonlocal model_path
        model_path = path

    model_loader.finished.connect(on_load_model)
    model_loader.run()
    return model_path
