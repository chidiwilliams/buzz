import os
import pytest

from buzz.model_loader import ModelDownloader,TranscriptionModel, ModelType, WhisperModelSize


class TestModelLoader:
    @pytest.mark.parametrize(
        "model",
        [
            TranscriptionModel(
                model_type=ModelType.HUGGING_FACE,
                hugging_face_model_id="RaivisDejus/whisper-tiny-lv",
            ),
        ],
    )
    def test_download_model(self, model: TranscriptionModel):
        model_loader = ModelDownloader(model=model)
        model_loader.run()

        model_path = model.get_local_model_path()

        assert model_path is not None, "Model path is None"
        assert os.path.isdir(model_path), "Model path is not a directory"
        assert len(os.listdir(model_path)) > 0, "Model directory is empty"
