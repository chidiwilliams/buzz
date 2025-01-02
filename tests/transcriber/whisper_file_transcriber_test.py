import glob
import logging
import os
import platform
import shutil
import sys
import tempfile
import time
from typing import List
from unittest.mock import Mock

import pytest
from pytestqt.qtbot import QtBot

from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import (
    OutputFormat,
    get_output_file_path,
    FileTranscriptionTask,
    TranscriptionOptions,
    Task,
    FileTranscriptionOptions,
    Segment,
)
from buzz.transcriber.whisper_file_transcriber import WhisperFileTranscriber
from tests.audio import test_audio_path
from tests.model_loader import get_model_path


class TestWhisperFileTranscriber:
    @pytest.mark.parametrize(
        "file_path,output_format,expected_file_path",
        [
            pytest.param(
                "/a/b/c.mp4",
                OutputFormat.SRT,
                "/a/b/c-translate--Whisper-tiny.srt",
                marks=pytest.mark.skipif(platform.system() == "Windows", reason=""),
            ),
            pytest.param(
                "C:\\a\\b\\c.mp4",
                OutputFormat.SRT,
                "C:\\a\\b\\c-translate--Whisper-tiny.srt",
                marks=pytest.mark.skipif(platform.system() != "Windows", reason=""),
            ),
        ],
    )
    def test_default_output_file(
        self,
        file_path: str,
        output_format: OutputFormat,
        expected_file_path: str,
    ):
        file_path = get_output_file_path(
            file_path=file_path,
            language=None,
            task=Task.TRANSLATE,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY,
            ),
            output_format=output_format,
            output_directory="",
            export_file_name_template="{{ input_file_name }}-{{ task }}-{{ language }}-{{ model_type }}-{{ model_size }}",
        )
        assert file_path == expected_file_path

    @pytest.mark.parametrize(
        "file_path,expected_starts_with",
        [
            pytest.param(
                "/a/b/c.mp4",
                "/a/b/c (Translated on ",
                marks=pytest.mark.skipif(platform.system() == "Windows", reason=""),
            ),
            pytest.param(
                "C:\\a\\b\\c.mp4",
                "C:\\a\\b\\c (Translated on ",
                marks=pytest.mark.skipif(platform.system() != "Windows", reason=""),
            ),
        ],
    )
    def test_default_output_file_with_date(
        self, file_path: str, expected_starts_with: str
    ):
        export_file_name_template = (
            "{{ input_file_name }} (Translated on {{ date_time }})"
        )
        srt = get_output_file_path(
            file_path=file_path,
            language=None,
            task=Task.TRANSLATE,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY,
            ),
            output_format=OutputFormat.TXT,
            output_directory="",
            export_file_name_template=export_file_name_template,
        )

        assert srt.startswith(expected_starts_with)
        assert srt.endswith(".txt")

        srt = get_output_file_path(
            file_path=file_path,
            language=None,
            task=Task.TRANSLATE,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY,
            ),
            output_format=OutputFormat.SRT,
            output_directory="",
            export_file_name_template=export_file_name_template,
        )
        assert srt.startswith(expected_starts_with)
        assert srt.endswith(".srt")

    @pytest.mark.parametrize(
        "word_level_timings,extract_speech,expected_segments,model",
        [
            (
                False,
                False,
                [
                    Segment(
                        0,
                        8400,
                        " Bienvenue dans Passe-Relle. Un podcast pensé pour évêiller",
                    )
                ],
                TranscriptionModel(
                    model_type=ModelType.WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
            ),
            (
                True,
                True,
                [Segment(40, 299, " Bien"), Segment(299, 329, "venue dans")],
                TranscriptionModel(
                    model_type=ModelType.WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
            ),
            (
                False,
                False,
                [
                    Segment(
                        0,
                        8517,
                        " Bienvenue dans Passe-Relle. Un podcast pensé pour évêyer la curiosité des apprenances "
                        "et des apprenances de français.",
                    )
                ],
                TranscriptionModel(
                    model_type=ModelType.HUGGING_FACE,
                    hugging_face_model_id="openai/whisper-tiny",
                ),
            ),
            pytest.param(
                False,
                False,
                [
                    Segment(
                        start=0,
                        end=8400,
                        text=" Bienvenue dans Passrel, un podcast pensé pour éveiller la curiosité des apprenances et des apprenances de français.",
                    )
                ],
                TranscriptionModel(
                    model_type=ModelType.FASTER_WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
                marks=pytest.mark.skipif(
                    platform.system() == "Darwin" and platform.machine() == "x86_64",
                    reason="Error with libiomp5 already initialized on GH action runner: https://github.com/chidiwilliams/buzz/actions/runs/4657331262/jobs/8241832087",
                ),
            ),
        ],
    )
    def test_transcribe_from_file(
        self,
        qtbot: QtBot,
        word_level_timings: bool,
        extract_speech: bool,
        expected_segments: List[Segment],
        model: TranscriptionModel,
    ):
        mock_progress = Mock()
        mock_completed = Mock()
        transcription_options = TranscriptionOptions(
            language="fr",
            task=Task.TRANSCRIBE,
            word_level_timings=word_level_timings,
            extract_speech=extract_speech,
            model=model,
        )
        model_path = get_model_path(transcription_options.model)
        file_path = os.path.abspath(test_audio_path)
        file_transcription_options = FileTranscriptionOptions(file_paths=[file_path])

        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=file_path,
                model_path=model_path,
            )
        )
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        with qtbot.wait_signal(
            transcriber.progress, timeout=10 * 6000
        ), qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        # Reports progress at 0, 0 <= progress <= 100, and 100
        assert mock_progress.call_count >= 2
        assert mock_progress.call_args_list[0][0][0] == (0, 100)

        mock_completed.assert_called()
        segments = mock_completed.call_args[0][0]
        assert len(segments) >= 0
        for i, expected_segment in enumerate(segments):
            assert segments[i].start >= 0
            assert segments[i].end > 0
            assert len(segments[i].text) > 0
            logging.debug(f"{segments[i].start} {segments[i].end} {segments[i].text}")

    def test_transcribe_from_url(self, qtbot):
        url = (
            "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3"
        )

        mock_progress = Mock()
        mock_completed = Mock()
        transcription_options = TranscriptionOptions()
        model_path = get_model_path(transcription_options.model)
        file_transcription_options = FileTranscriptionOptions(url=url)

        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                model_path=model_path,
                url=url,
                source=FileTranscriptionTask.Source.URL_IMPORT,
            )
        )
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        with qtbot.wait_signal(
            transcriber.progress, timeout=10 * 6000
        ), qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        # Reports progress at 0, 0 <= progress <= 100, and 100
        assert mock_progress.call_count >= 2
        assert mock_progress.call_args_list[0][0][0] == (0, 100)

        mock_completed.assert_called()
        segments = mock_completed.call_args[0][0]
        assert len(segments) >= 0
        for i, expected_segment in enumerate(segments):
            assert segments[i].start >= 0
            assert segments[i].end > 0
            assert len(segments[i].text) > 0
            logging.debug(f"{segments[i].start} {segments[i].end} {segments[i].text}")

    def test_transcribe_from_folder_watch_source(self, qtbot):
        file_path = tempfile.mktemp(suffix=".mp3")
        shutil.copy(test_audio_path, file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=[file_path],
            output_formats={OutputFormat.TXT},
        )
        transcription_options = TranscriptionOptions()
        model_path = get_model_path(transcription_options.model)

        output_directory = tempfile.mkdtemp()
        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                model_path=model_path,
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=file_path,
                output_directory=output_directory,
                source=FileTranscriptionTask.Source.FOLDER_WATCH,
            )
        )
        with qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        assert not os.path.isfile(file_path)
        assert os.path.isfile(
            os.path.join(output_directory, os.path.basename(file_path))
        )
        assert len(glob.glob("*.txt", root_dir=output_directory)) > 0

    @pytest.mark.skip()
    def test_transcribe_stop(self):
        output_file_path = os.path.join(tempfile.gettempdir(), "whisper.txt")
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=[test_audio_path]
        )
        transcription_options = TranscriptionOptions(
            language="fr",
            task=Task.TRANSCRIBE,
            word_level_timings=False,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            ),
        )
        model_path = get_model_path(transcription_options.model)

        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                model_path=model_path,
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=test_audio_path,
            )
        )
        transcriber.run()
        time.sleep(1)
        transcriber.stop()

        # Assert that file was not created
        assert os.path.isfile(output_file_path) is False
