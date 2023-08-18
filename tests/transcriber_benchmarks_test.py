import platform
from unittest.mock import Mock

import pytest

from buzz.model_loader import WhisperModelSize, ModelType, TranscriptionModel
from buzz.transcriber import (
    FileTranscriptionOptions,
    FileTranscriptionTask,
    Task,
    WhisperCppFileTranscriber,
    TranscriptionOptions,
    WhisperFileTranscriber,
    FileTranscriber,
)
from tests.model_loader import get_model_path


def get_task(model: TranscriptionModel):
    file_transcription_options = FileTranscriptionOptions(
        file_paths=["testdata/whisper-french.mp3"]
    )
    transcription_options = TranscriptionOptions(
        language="fr", task=Task.TRANSCRIBE, word_level_timings=False, model=model
    )
    model_path = get_model_path(transcription_options.model)
    return FileTranscriptionTask(
        file_path="testdata/audio-long.mp3",
        transcription_options=transcription_options,
        file_transcription_options=file_transcription_options,
        model_path=model_path,
    )


def transcribe(qtbot, transcriber: FileTranscriber):
    mock_completed = Mock()
    transcriber.completed.connect(mock_completed)
    with qtbot.waitSignal(transcriber.completed, timeout=10 * 60 * 1000):
        transcriber.run()

    segments = mock_completed.call_args[0][0]
    return segments


@pytest.mark.parametrize(
    "transcriber",
    [
        pytest.param(
            WhisperCppFileTranscriber(
                task=(
                    get_task(
                        TranscriptionModel(
                            model_type=ModelType.WHISPER_CPP,
                            whisper_model_size=WhisperModelSize.TINY,
                        )
                    )
                )
            ),
            id="Whisper.cpp - Tiny",
        ),
        pytest.param(
            WhisperFileTranscriber(
                task=(
                    get_task(
                        TranscriptionModel(
                            model_type=ModelType.WHISPER,
                            whisper_model_size=WhisperModelSize.TINY,
                        )
                    )
                )
            ),
            id="Whisper - Tiny",
        ),
        pytest.param(
            WhisperFileTranscriber(
                task=(
                    get_task(
                        TranscriptionModel(
                            model_type=ModelType.FASTER_WHISPER,
                            whisper_model_size=WhisperModelSize.TINY,
                        )
                    )
                )
            ),
            id="Faster Whisper - Tiny",
            marks=pytest.mark.skipif(
                platform.system() == "Darwin",
                reason="Error with libiomp5 already initialized on GH action runner: https://github.com/chidiwilliams/buzz/actions/runs/4657331262/jobs/8241832087",
            ),
        ),
    ],
)
def test_should_transcribe_and_benchmark(qtbot, benchmark, transcriber):
    segments = benchmark(transcribe, qtbot, transcriber)
    assert len(segments) > 0
