import logging
import os
import pathlib
import platform
import shutil
import sys
import tempfile
import time
from typing import List
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import QThread
from pytestqt.qtbot import QtBot

from buzz.model_loader import WhisperModelSize, ModelType, TranscriptionModel
from buzz.transcriber import (
    FileTranscriptionOptions,
    FileTranscriptionTask,
    OutputFormat,
    Segment,
    Task,
    WhisperCpp,
    WhisperCppFileTranscriber,
    WhisperFileTranscriber,
    get_output_file_path,
    to_timestamp,
    whisper_cpp_params,
    write_output,
    TranscriptionOptions,
    OpenAIWhisperAPIFileTranscriber,
)
from buzz.recording_transcriber import RecordingTranscriber
from tests.mock_sounddevice import MockInputStream
from tests.model_loader import get_model_path


class TestRecordingTranscriber:
    @pytest.mark.skip(reason="Hanging")
    def test_should_transcribe(self, qtbot):
        thread = QThread()

        transcription_model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY
        )

        transcriber = RecordingTranscriber(
            transcription_options=TranscriptionOptions(
                model=transcription_model, language="fr", task=Task.TRANSCRIBE
            ),
            input_device_index=0,
            sample_rate=16_000,
        )
        transcriber.moveToThread(thread)

        thread.finished.connect(thread.deleteLater)

        mock_transcription = Mock()
        transcriber.transcription.connect(mock_transcription)

        transcriber.finished.connect(thread.quit)
        transcriber.finished.connect(transcriber.deleteLater)

        with patch("sounddevice.InputStream", side_effect=MockInputStream), patch(
            "sounddevice.check_input_settings"
        ), qtbot.wait_signal(transcriber.transcription, timeout=60 * 1000):
            thread.start()

        with qtbot.wait_signal(thread.finished, timeout=60 * 1000):
            transcriber.stop_recording()

        text = mock_transcription.call_args[0][0]
        assert "Bienvenue dans Passe" in text


class TestOpenAIWhisperAPIFileTranscriber:
    def test_transcribe(self):
        file_path = "testdata/whisper-french.mp3"
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
        mock_openai_result = {"segments": [{"start": 0, "end": 6.56, "text": "Hello"}]}
        with patch("openai.Audio.transcribe", return_value=mock_openai_result):
            transcriber.run()

        called_segments = mock_completed.call_args[0][0]

        assert len(called_segments) == 1
        assert called_segments[0].start == 0
        assert called_segments[0].end == 6560
        assert called_segments[0].text == "Hello"


class TestWhisperCppFileTranscriber:
    @pytest.mark.parametrize(
        "word_level_timings,expected_segments",
        [
            (
                False,
                [Segment(0, 6560, "Bienvenue dans Passe-Relle. Un podcast pensé pour")],
            ),
            (True, [Segment(30, 330, "Bien"), Segment(330, 740, "venue")]),
        ],
    )
    def test_transcribe(
        self, qtbot: QtBot, word_level_timings: bool, expected_segments: List[Segment]
    ):
        file_transcription_options = FileTranscriptionOptions(
            file_paths=["testdata/whisper-french.mp3"]
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
                file_path="testdata/whisper-french.mp3",
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

        with qtbot.waitSignal(
            [transcriber.completed, transcriber.error], timeout=10 * 60 * 1000
        ):
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


class TestWhisperFileTranscriber:
    @pytest.mark.parametrize(
        "file_path,output_format,expected_file_path,default_output_file_name",
        [
            pytest.param(
                "/a/b/c.mp4",
                OutputFormat.SRT,
                "/a/b/c-translate--Whisper-tiny.srt",
                "{{ input_file_name }}-{{ task }}-{{ language }}-{{ model_type }}-{{ model_size }}",
                marks=pytest.mark.skipif(platform.system() == "Windows", reason=""),
            ),
            pytest.param(
                "C:\\a\\b\\c.mp4",
                OutputFormat.SRT,
                "C:\\a\\b\\c-translate--Whisper-tiny.srt",
                "{{ input_file_name }}-{{ task }}-{{ language }}-{{ model_type }}-{{ model_size }}",
                marks=pytest.mark.skipif(platform.system() != "Windows", reason=""),
            ),
        ],
    )
    def test_default_output_file(
        self,
        file_path: str,
        output_format: OutputFormat,
        expected_file_path: str,
        default_output_file_name: str,
    ):
        file_path = get_output_file_path(
            task=FileTranscriptionTask(
                file_path=file_path,
                transcription_options=TranscriptionOptions(task=Task.TRANSLATE),
                file_transcription_options=FileTranscriptionOptions(
                    file_paths=[], default_output_file_name=default_output_file_name
                ),
                model_path="",
            ),
            output_format=output_format,
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
        srt = get_output_file_path(
            task=FileTranscriptionTask(
                file_path=file_path,
                transcription_options=TranscriptionOptions(task=Task.TRANSLATE),
                file_transcription_options=FileTranscriptionOptions(
                    file_paths=[],
                    default_output_file_name="{{ input_file_name }} (Translated on {{ date_time }})",
                ),
                model_path="",
            ),
            output_format=OutputFormat.TXT,
        )

        assert srt.startswith(expected_starts_with)
        assert srt.endswith(".txt")

        srt = get_output_file_path(
            task=FileTranscriptionTask(
                file_path=file_path,
                transcription_options=TranscriptionOptions(task=Task.TRANSLATE),
                file_transcription_options=FileTranscriptionOptions(
                    file_paths=[],
                    default_output_file_name="{{ input_file_name }} (Translated on {{ date_time }})",
                ),
                model_path="",
            ),
            output_format=OutputFormat.SRT,
        )
        assert srt.startswith(expected_starts_with)
        assert srt.endswith(".srt")

    @pytest.mark.parametrize(
        "word_level_timings,expected_segments,model",
        [
            (
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
                [Segment(40, 299, " Bien"), Segment(299, 329, "venue dans")],
                TranscriptionModel(
                    model_type=ModelType.WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
            ),
            (
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
                    platform.system() == "Darwin",
                    reason="Error with libiomp5 already initialized on GH action runner: https://github.com/chidiwilliams/buzz/actions/runs/4657331262/jobs/8241832087",
                ),
            ),
        ],
    )
    @pytest.mark.skipif(
        sys.platform == "linux", reason="Avoid execstack errors on Snap"
    )
    def test_transcribe(
        self,
        qtbot: QtBot,
        word_level_timings: bool,
        expected_segments: List[Segment],
        model: TranscriptionModel,
    ):
        mock_progress = Mock()
        mock_completed = Mock()
        transcription_options = TranscriptionOptions(
            language="fr",
            task=Task.TRANSCRIBE,
            word_level_timings=word_level_timings,
            model=model,
        )
        model_path = get_model_path(transcription_options.model)
        file_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "testdata/whisper-french.mp3")
        )
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

    @pytest.mark.skipif(
        sys.platform == "linux", reason="Avoid execstack errors on Snap"
    )
    def test_transcribe_from_folder_watch_source(self, qtbot):
        file_path = tempfile.mktemp(suffix=".mp3")
        shutil.copy("testdata/whisper-french.mp3", file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=[file_path],
            output_formats={OutputFormat.TXT},
            default_output_file_name="{{ input_file_name }}",
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
        assert os.path.isfile(
            os.path.join(
                output_directory,
                os.path.splitext(os.path.basename(file_path))[0] + ".txt",
            )
        )

    @pytest.mark.skip()
    def test_transcribe_stop(self):
        output_file_path = os.path.join(tempfile.gettempdir(), "whisper.txt")
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=["testdata/whisper-french.mp3"]
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
                file_path="testdata/whisper-french.mp3",
            )
        )
        transcriber.run()
        time.sleep(1)
        transcriber.stop()

        # Assert that file was not created
        assert os.path.isfile(output_file_path) is False


class TestToTimestamp:
    def test_to_timestamp(self):
        assert to_timestamp(0) == "00:00:00.000"
        assert to_timestamp(123456789) == "34:17:36.789"


class TestWhisperCpp:
    def test_transcribe(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            )
        )
        model_path = get_model_path(transcription_options.model)

        whisper_cpp = WhisperCpp(model=model_path)
        params = whisper_cpp_params(
            language="fr", task=Task.TRANSCRIBE, word_level_timings=False
        )
        result = whisper_cpp.transcribe(
            audio="testdata/whisper-french.mp3", params=params
        )

        assert "Bienvenue dans Passe" in result["text"]


@pytest.mark.parametrize(
    "output_format,output_text",
    [
        (OutputFormat.TXT, "Bien\nvenue dans\n"),
        (
            OutputFormat.SRT,
            "1\n00:00:00,040 --> 00:00:00,299\nBien\n\n2\n00:00:00,299 --> 00:00:00,329\nvenue dans\n\n",
        ),
        (
            OutputFormat.VTT,
            "WEBVTT\n\n00:00:00.040 --> 00:00:00.299\nBien\n\n00:00:00.299 --> 00:00:00.329\nvenue dans\n\n",
        ),
    ],
)
def test_write_output(
    tmp_path: pathlib.Path, output_format: OutputFormat, output_text: str
):
    output_file_path = tmp_path / "whisper.txt"
    segments = [Segment(40, 299, "Bien"), Segment(299, 329, "venue dans")]

    write_output(
        path=str(output_file_path), segments=segments, output_format=output_format
    )

    output_file = open(output_file_path, "r", encoding="utf-8")
    assert output_text == output_file.read()
