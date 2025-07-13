import os
from typing import List
from unittest.mock import Mock
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import (
    Segment,
    FileTranscriptionOptions,
    TranscriptionOptions,
    Task,
    FileTranscriptionTask,
)
from buzz.transcriber.whisper_cpp_file_transcriber import WhisperCppFileTranscriber
from tests.audio import test_audio_path, test_multibyte_utf8_audio_path
from tests.model_loader import get_model_path


class TestWhisperCppFileTranscriber:
    @pytest.mark.parametrize(
        "word_level_timings,expected_segments",
        [
            (
                False,
                [Segment(0, 6560, "Bienvenue dans Passe-Relle. Un podcast pensé pour")],
            ),
            (True, [Segment(30, 740, "Bienvenue"), Segment(740, 1070, "dans")]),
        ],
    )
    def test_transcribe(
        self, qtbot: QtBot, word_level_timings: bool, expected_segments: List[Segment]
    ):
        os.environ["BUZZ_FORCE_CPU"] = "true"
        file_transcription_options = FileTranscriptionOptions(
            file_paths=[str(Path(test_audio_path).resolve())]
        )
        transcription_options = TranscriptionOptions(
            language="fr",
            task=Task.TRANSCRIBE,
            word_level_timings=word_level_timings,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            ),
        )

        model_path = get_model_path(transcription_options.model)
        transcriber = WhisperCppFileTranscriber(
            task=FileTranscriptionTask(
                file_path=str(Path(test_audio_path).resolve()),
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                model_path=model_path,
            )
        )
        mock_progress = Mock(side_effect=lambda value: print("progress: ", value))
        mock_completed = Mock()
        mock_error = Mock()
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        transcriber.error.connect(mock_error)

        with qtbot.wait_signal(transcriber.completed, timeout=10 * 60 * 1000):
            transcriber.run()

        mock_error.assert_not_called()

        mock_progress.assert_called()
        segments = [
            segment
            for segment in mock_completed.call_args[0][0]
            if len(segment.text) > 0
        ]
        for i, expected_segment in enumerate(expected_segments):
            assert expected_segment.start == segments[i].start
            assert expected_segment.end == segments[i].end
            assert expected_segment.text in segments[i].text

        transcriber.stop()

    @pytest.mark.parametrize(
        "word_level_timings,expected_segments",
        [
            (
                False,
                [Segment(0, 7000, "Mani uzstrauts, laikabstākļi, tapēc uz jūru, es diezvajī braukša.")],
            ),
            (True, [Segment(380, 500, "Mani"), Segment(500, 1880, "uzstrauts,"), Segment(1880, 3920, "laikabstākļi")]),
        ],
    )
    # Problematic part is in "laikabstākļi" where "ļ" gets returned from whisper.cpp in two segments
    # First segment has first byte b'\xc4' and the second has second byte b'\xbc'.
    def test_transcribe_latvian(
        self, qtbot: QtBot, word_level_timings: bool, expected_segments: List[Segment]
    ):
        os.environ["BUZZ_FORCE_CPU"] = "true"
        file_transcription_options = FileTranscriptionOptions(
            file_paths=[str(Path(test_multibyte_utf8_audio_path).resolve())]
        )
        transcription_options = TranscriptionOptions(
            language="lv",
            task=Task.TRANSCRIBE,
            word_level_timings=word_level_timings,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            ),
        )

        model_path = get_model_path(transcription_options.model)
        transcriber = WhisperCppFileTranscriber(
            task=FileTranscriptionTask(
                file_path=str(Path(test_multibyte_utf8_audio_path).resolve()),
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                model_path=model_path,
            )
        )
        mock_progress = Mock(side_effect=lambda value: print("progress: ", value))
        mock_completed = Mock()
        mock_error = Mock()
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        transcriber.error.connect(mock_error)

        with qtbot.wait_signal(transcriber.completed, timeout=10 * 60 * 1000):
            transcriber.run()

        mock_error.assert_not_called()

        mock_progress.assert_called()
        segments = [
            segment
            for segment in mock_completed.call_args[0][0]
            if len(segment.text) > 0
        ]
        for i, expected_segment in enumerate(expected_segments):
            assert expected_segment.start == segments[i].start
            assert expected_segment.end == segments[i].end
            assert expected_segment.text in segments[i].text

        transcriber.stop()
