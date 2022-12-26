from buzz.model_loader import ModelLoader, TranscriptionModel


def get_model_path(transcription_model: TranscriptionModel) -> str:
    model_loader = ModelLoader(model=transcription_model)
    model_path = ''

    def on_load_model(path: str):
        nonlocal model_path
        model_path = path

    model_loader.finished.connect(on_load_model)
    model_loader.run()
    return model_path
