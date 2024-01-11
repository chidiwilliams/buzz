import os
from unittest.mock import patch, Mock

import pytest

from buzz.transcriber.openai_whisper_api_file_transcriber import (
    OpenAIWhisperAPIFileTranscriber,
)
from buzz.transcriber.transcriber import (
    FileTranscriptionTask,
    TranscriptionOptions,
    FileTranscriptionOptions,
)

from openai.types.audio import Transcription, Translation


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
