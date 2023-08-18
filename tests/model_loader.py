from buzz.model_loader import TranscriptionModel, ModelDownloader


def get_model_path(transcription_model: TranscriptionModel) -> str:
    path = transcription_model.get_local_model_path()
    if path is not None:
        return path

    model_loader = ModelDownloader(model=transcription_model)
    model_path = ""

    def on_load_model(path: str):
        nonlocal model_path
        model_path = path

    model_loader.signals.finished.connect(on_load_model)
    model_loader.run()
    return model_path
