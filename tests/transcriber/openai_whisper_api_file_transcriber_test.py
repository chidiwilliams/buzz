import os
from unittest.mock import patch, Mock

import pytest

from buzz.model_loader import ModelType, TranscriptionModel
from buzz.transcriber.openai_whisper_api_file_transcriber import (
    OpenAIWhisperAPIFileTranscriber,
    append_segment,
)
from buzz.transcriber.transcriber import (
    FileTranscriptionTask,
    TranscriptionOptions,
    FileTranscriptionOptions,
    Segment,
)

from openai.types.audio import Transcription, Translation


class TestAppendSegment:
    def test_valid_utf8(self):
        result = []
        success = append_segment(result, b"Hello world", 100, 200)
        assert success is True
        assert len(result) == 1
        assert result[0].start == 1000  # 100 centiseconds to ms
        assert result[0].end == 2000    # 200 centiseconds to ms
        assert result[0].text == "Hello world"

    def test_empty_bytes(self):
        result = []
        success = append_segment(result, b"", 100, 200)
        assert success is True
        assert len(result) == 0

    def test_invalid_utf8(self):
        result = []
        # Invalid UTF-8 sequence
        success = append_segment(result, b"\xff\xfe", 100, 200)
        assert success is False
        assert len(result) == 0

    def test_multibyte_utf8(self):
        result = []
        success = append_segment(result, "Привет".encode("utf-8"), 50, 150)
        assert success is True
        assert len(result) == 1
        assert result[0].text == "Привет"


class TestGetValue:
    def test_get_value_from_dict(self):
        obj = {"key": "value", "number": 42}
        assert OpenAIWhisperAPIFileTranscriber.get_value(obj, "key") == "value"
        assert OpenAIWhisperAPIFileTranscriber.get_value(obj, "number") == 42

    def test_get_value_from_object(self):
        class TestObj:
            key = "value"
            number = 42

        obj = TestObj()
        assert OpenAIWhisperAPIFileTranscriber.get_value(obj, "key") == "value"
        assert OpenAIWhisperAPIFileTranscriber.get_value(obj, "number") == 42

    def test_get_value_missing_key_dict(self):
        obj = {"key": "value"}
        assert OpenAIWhisperAPIFileTranscriber.get_value(obj, "missing") is None
        assert OpenAIWhisperAPIFileTranscriber.get_value(obj, "missing", "default") == "default"

    def test_get_value_missing_attribute_object(self):
        class TestObj:
            key = "value"

        obj = TestObj()
        assert OpenAIWhisperAPIFileTranscriber.get_value(obj, "missing") is None
        assert OpenAIWhisperAPIFileTranscriber.get_value(obj, "missing", "default") == "default"


class TestOpenAIWhisperAPIFileTranscriber:
    @pytest.fixture
    def mock_openai_client(self):
        with patch(
            "buzz.transcriber.openai_whisper_api_file_transcriber.OpenAI"
        ) as mock:
            return_value = {
                "text": "",
                "segments": [{"start": 0, "end": 6.56, "text": "Hello"}],
            }
            mock.return_value.audio.transcriptions.create.return_value = Transcription(
                **return_value
            )
            mock.return_value.audio.translations.create.return_value = Translation(
                **return_value
            )
            yield mock

    def test_transcribe(self, mock_openai_client):
        file_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../testdata/whisper-french.mp3",
        )
        transcriber = OpenAIWhisperAPIFileTranscriber(
            task=FileTranscriptionTask(
                file_path=file_path,
                transcription_options=(
                    TranscriptionOptions(
                        openai_access_token=os.getenv("OPENAI_ACCESS_TOKEN"),
                    )
                ),
                file_transcription_options=(
                    FileTranscriptionOptions(file_paths=[file_path])
                ),
                model_path="",
            )
        )
        mock_completed = Mock()
        transcriber.completed.connect(mock_completed)
        transcriber.run()

        mock_openai_client.return_value.audio.transcriptions.create.assert_called()

        called_segments = mock_completed.call_args[0][0]

        assert len(called_segments) == 1
        assert called_segments[0].start == 0
        assert called_segments[0].end == 6560
        assert called_segments[0].text == "Hello"

    def test_funasr_client_uses_dedicated_defaults(self, monkeypatch):
        monkeypatch.delenv("BUZZ_FUNASR_BASE_URL", raising=False)
        monkeypatch.delenv("BUZZ_FUNASR_MODEL", raising=False)
        monkeypatch.delenv("BUZZ_FUNASR_API_KEY", raising=False)

        task = FileTranscriptionTask(
            transcription_options=TranscriptionOptions(
                model=TranscriptionModel(model_type=ModelType.FUNASR_API),
                openai_access_token="sk-must-not-leak",
            ),
            file_transcription_options=FileTranscriptionOptions(),
            model_path="",
        )

        with patch(
            "buzz.transcriber.openai_whisper_api_file_transcriber.Settings"
        ) as mock_settings, patch(
            "buzz.transcriber.openai_whisper_api_file_transcriber.OpenAI"
        ) as mock_openai:
            mock_settings.return_value.value.side_effect = (
                lambda key, default_value: default_value
            )
            transcriber = OpenAIWhisperAPIFileTranscriber(task=task)

        mock_openai.assert_called_once_with(
            api_key="not-needed",
            base_url="http://localhost:8000/v1",
            max_retries=0,
        )
        assert transcriber.whisper_api_model == "sensevoice"

    def test_funasr_empty_segments_fall_back_to_text(self, monkeypatch):
        monkeypatch.delenv("BUZZ_FUNASR_BASE_URL", raising=False)
        monkeypatch.delenv("BUZZ_FUNASR_MODEL", raising=False)
        monkeypatch.delenv("BUZZ_FUNASR_API_KEY", raising=False)
        file_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../testdata/whisper-french.mp3",
        )
        task = FileTranscriptionTask(
            file_path=file_path,
            transcription_options=TranscriptionOptions(
                model=TranscriptionModel(model_type=ModelType.FUNASR_API),
                initial_prompt="must not be sent",
                openai_access_token="sk-must-not-leak",
            ),
            file_transcription_options=FileTranscriptionOptions(
                file_paths=[file_path]
            ),
            model_path="",
        )

        with patch(
            "buzz.transcriber.openai_whisper_api_file_transcriber.Settings"
        ) as mock_settings, patch(
            "buzz.transcriber.openai_whisper_api_file_transcriber.OpenAI"
        ) as mock_openai:
            mock_settings.return_value.value.side_effect = (
                lambda key, default_value: default_value
            )
            mock_openai.return_value.audio.transcriptions.create.return_value = (
                Transcription(text="欢迎使用 FunASR", segments=[])
            )
            transcriber = OpenAIWhisperAPIFileTranscriber(task=task)
            segments = transcriber.get_segments_for_file(file_path)

        assert segments == [Segment(start=0, end=0, text="欢迎使用 FunASR")]
        call_options = mock_openai.return_value.audio.transcriptions.create.call_args.kwargs
        assert call_options["model"] == "sensevoice"
        assert call_options["response_format"] == "verbose_json"
        assert "prompt" not in call_options
        mock_openai.return_value.audio.translations.create.assert_not_called()
