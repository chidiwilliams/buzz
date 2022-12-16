import logging
import os
import pathlib
import tempfile
import time
from typing import List
from unittest.mock import Mock

from PyQt6.QtCore import QCoreApplication
import pytest
from pytestqt.qtbot import QtBot

from buzz.model_loader import ModelLoader
from buzz.transcriber import (FileTranscriptionOptions, OutputFormat, RecordingTranscriber, Segment, Task,
                              WhisperCpp, WhisperCppFileTranscriber,
                              WhisperFileTranscriber,
                              get_default_output_file_path, to_timestamp,
                              whisper_cpp_params, write_output)


def get_model_path(model_name: str, use_whisper_cpp: bool) -> str:
    model_loader = ModelLoader(model_name, use_whisper_cpp)
    model_path = ''

    def on_load_model(path: str):
        nonlocal model_path
        model_path = path

    model_loader.finished.connect(on_load_model)
    model_loader.run()
    return model_path


class TestRecordingTranscriber:
    def test_transcriber(self):
        model_path = get_model_path('tiny', True)
        transcriber = RecordingTranscriber(
            model_path=model_path, use_whisper_cpp=True, language='en',
            task=Task.TRANSCRIBE)
        assert transcriber is not None


class TestWhisperCppFileTranscriber:
    @pytest.mark.parametrize(
        'word_level_timings,expected_segments',
        [
            (False, [Segment(0, 1840, 'Bienvenue dans Passe Relle.')]),
            (True, [Segment(30, 280, 'Bien'), Segment(280, 630, 'venue')])
        ])
    def test_transcribe(self, qtbot: QtBot, word_level_timings: bool, expected_segments: List[Segment]):
        transcription_options = FileTranscriptionOptions(
            language='fr', task=Task.TRANSCRIBE, file_path='testdata/whisper-french.mp3',
            word_level_timings=word_level_timings)

        model_path = get_model_path('tiny', True)
        transcriber = WhisperCppFileTranscriber(
            transcription_options=transcription_options)
        mock_progress = Mock()
        mock_completed = Mock()
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        with qtbot.waitSignal(transcriber.completed, timeout=10 * 60 * 1000):
            transcriber.run(model_path)

        mock_progress.assert_called()
        exit_code, segments = mock_completed.call_args[0][0]
        assert exit_code is 0
        for expected_segment in expected_segments:
            assert expected_segment in segments


class TestWhisperFileTranscriber:
    def test_default_output_file(self):
        srt = get_default_output_file_path(
            Task.TRANSLATE, '/a/b/c.mp4', OutputFormat.TXT)
        assert srt.startswith('/a/b/c (Translated on ')
        assert srt.endswith('.txt')

        srt = get_default_output_file_path(
            Task.TRANSLATE, '/a/b/c.mp4', OutputFormat.SRT)
        assert srt.startswith('/a/b/c (Translated on ')
        assert srt.endswith('.srt')

    @pytest.mark.parametrize(
        'word_level_timings,expected_segments',
        [
            (False, [
                Segment(
                    0, 6560,
                    ' Bienvenue dans Passe-Relle. Un podcast pensé pour évêiller la curiosité des apprenances'),
            ]),
            (True, [Segment(40, 299, ' Bien'), Segment(299, 329, 'venue dans')])
        ])
    def test_transcribe(self, qtbot: QtBot, word_level_timings: bool, expected_segments: List[Segment]):
        model_path = get_model_path('tiny', False)

        mock_progress = Mock()
        mock_completed = Mock()
        transcription_options = FileTranscriptionOptions(
            language='fr', task=Task.TRANSCRIBE, file_path='testdata/whisper-french.mp3',
            word_level_timings=word_level_timings)

        transcriber = WhisperFileTranscriber(
            transcription_options=transcription_options)
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        with qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run(model_path)

        QCoreApplication.processEvents()

        # Reports progress at 0, 0<progress<100, and 100
        assert any(
            [call_args.args[0] == (0, 100) for call_args in mock_progress.call_args_list])
        assert any(
            [call_args.args[0] == (100, 100) for call_args in mock_progress.call_args_list])
        assert any(
            [(0 < call_args.args[0][0] < 100) and (call_args.args[0][1] == 100) for call_args in
             mock_progress.call_args_list])

        mock_completed.assert_called()
        exit_code, segments = mock_completed.call_args[0][0]
        assert exit_code is 0
        for (i, expected_segment) in enumerate(expected_segments):
            assert segments[i] == expected_segment

    @pytest.mark.skip()
    def test_transcribe_stop(self):
        output_file_path = os.path.join(tempfile.gettempdir(), 'whisper.txt')
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        model_path = get_model_path('tiny', False)
        transcription_options = FileTranscriptionOptions(
            language='fr', task=Task.TRANSCRIBE, file_path='testdata/whisper-french.mp3',
            word_level_timings=False)

        transcriber = WhisperFileTranscriber(
            transcription_options=transcription_options)
        transcriber.run(model_path)
        time.sleep(1)
        transcriber.stop()

        # Assert that file was not created
        assert os.path.isfile(output_file_path) is False


class TestToTimestamp:
    def test_to_timestamp(self):
        assert to_timestamp(0) == '00:00:00.000'
        assert to_timestamp(123456789) == '34:17:36.789'


class TestWhisperCpp:
    def test_transcribe(self):
        model_path = get_model_path('tiny', True)

        whisper_cpp = WhisperCpp(model=model_path)
        params = whisper_cpp_params(
            language='fr', task=Task.TRANSCRIBE, word_level_timings=False)
        result = whisper_cpp.transcribe(
            audio='testdata/whisper-french.mp3', params=params)

        assert 'Bienvenue dans Passe' in result['text']


@pytest.mark.parametrize(
    'output_format,output_text',
    [
        (OutputFormat.TXT, 'Bien venue dans\n'),
        (
                OutputFormat.SRT,
                '1\n00:00:00.040 --> 00:00:00.299\nBien\n\n2\n00:00:00.299 --> 00:00:00.329\nvenue dans\n\n'),
        (OutputFormat.VTT,
         'WEBVTT\n\n00:00:00.040 --> 00:00:00.299\nBien\n\n00:00:00.299 --> 00:00:00.329\nvenue dans\n\n'),
    ])
def test_write_output(tmp_path: pathlib.Path, output_format: OutputFormat, output_text: str):
    output_file_path = tmp_path / 'whisper.txt'
    segments = [Segment(40, 299, 'Bien'), Segment(299, 329, 'venue dans')]

    write_output(path=str(output_file_path), segments=segments,
                 should_open=False, output_format=output_format)

    output_file = open(output_file_path, 'r', encoding='utf-8')
    assert output_text == output_file.read()
