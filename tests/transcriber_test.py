import logging
import os
import pathlib
import tempfile
import time
from unittest.mock import Mock

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import QCoreApplication

from buzz.model_loader import ModelLoader
from buzz.transcriber import (OutputFormat, RecordingTranscriber, Task,
                              WhisperCpp, WhisperCppFileTranscriber,
                              WhisperFileTranscriber,
                              get_default_output_file_path, to_timestamp,
                              whisper_cpp_params)
from .sd import sounddevice_mocks


class TestRecordingTranscriber:
    def test_transcriber(self, qtbot: QtBot):
        model_path = get_model_path('tiny', True)
        with sounddevice_mocks():
            mock_transcription = Mock()

            transcriber = RecordingTranscriber(
                use_whisper_cpp=True, language='fr', task=Task.TRANSCRIBE)
            transcriber.transcription.connect(mock_transcription)

            with qtbot.wait_signal(transcriber.transcription, timeout=30*1000, check_params_cb=call_counter(2)):
                transcriber.run(model_path)

            transcriber.stop()

            mock_transcription.assert_any_call(
                'Bienvenue dans Passe Rail. Un podcast pensé pour évayer la curiosité.')
            mock_transcription.assert_any_call(
                'Les apprenances et des apprenances de français.')


class TestWhisperCppFileTranscriber:
    @pytest.mark.parametrize(
        'task,output_text',
        [
            (Task.TRANSCRIBE, 'Bienvenue dans Passe-Relle, un podcast'),
            (Task.TRANSLATE, 'Welcome to Passe-Relle, a podcast'),
        ])
    def test_transcribe(self, qtbot, tmp_path: pathlib.Path, task: Task, output_text: str):
        output_file_path = tmp_path / 'whisper_cpp.txt'
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        model_path = get_model_path('tiny', True)
        transcriber = WhisperCppFileTranscriber(
            language='fr', task=task, file_path='testdata/whisper-french.mp3',
            output_file_path=output_file_path.as_posix(), output_format=OutputFormat.TXT,
            open_file_on_complete=False,
            word_level_timings=False)
        mock_progress = Mock()
        with qtbot.waitSignal(transcriber.completed, timeout=10*60*1000):
            transcriber.progress.connect(mock_progress)
            transcriber.run(model_path)

        assert os.path.isfile(output_file_path)

        output_file = open(output_file_path, 'r', encoding='utf-8')
        assert output_text in output_file.read()

        mock_progress.assert_called()


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
        'word_level_timings,output_format,output_text',
        [
            (False, OutputFormat.TXT, 'Bienvenue dans Passe-Relle, un podcast'),
            (False, OutputFormat.SRT, '1\n00:00:00.000 --> 00:00:06.560\n Bienvenue dans Passe-Relle, un podcast pensé pour évêyer la curiosité des apprenances'),
            (False, OutputFormat.VTT, 'WEBVTT\n\n00:00:00.000 --> 00:00:06.560\n Bienvenue dans Passe-Relle, un podcast pensé pour évêyer la curiosité des apprenances'),
            (True, OutputFormat.SRT,
             '1\n00:00:00.040 --> 00:00:00.359\n Bienvenue dans\n\n2\n00:00:00.359 --> 00:00:00.419\n Passe-'),
        ])
    def test_transcribe(self, qtbot, tmp_path: pathlib.Path, word_level_timings: bool, output_format: OutputFormat, output_text: str):
        output_file_path = tmp_path / f'whisper.{output_format.value.lower()}'

        model_path = get_model_path('tiny', False)

        mock_progress = Mock()
        transcriber = WhisperFileTranscriber(
            language='fr', task=Task.TRANSCRIBE, file_path='testdata/whisper-french.mp3',
            output_file_path=output_file_path.as_posix(), output_format=output_format,
            open_file_on_complete=False, word_level_timings=word_level_timings)
        transcriber.progress.connect(mock_progress)
        with qtbot.wait_signal(transcriber.completed, timeout=30*1000):
            transcriber.run(model_path)

        assert os.path.isfile(output_file_path)

        output_file = open(output_file_path, 'r', encoding='utf-8')
        assert output_text in output_file.read()

        # TODO: Not working because test isn't running in a thread with event loop processing.
        # Fix here or move progress checking to GUI tests
        # Reports progress at 0, 0<progress<100, and 100
        # assert any(
        #     [call_args.args[0] == (0, 100) for call_args in mock_progress.call_args_list])
        # assert any(
        #     [call_args.args[0] == (100, 100) for call_args in mock_progress.call_args_list])
        # assert any(
        #     [(0 < call_args.args[0][0] < 100) and (call_args.args[0][1] == 100) for call_args in mock_progress.call_args_list])

    @pytest.mark.skip()
    def test_transcribe_stop(self):
        output_file_path = os.path.join(tempfile.gettempdir(), 'whisper.txt')
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        model_path = get_model_path('tiny', False)
        transcriber = WhisperFileTranscriber(
            language='fr', task=Task.TRANSCRIBE, file_path='testdata/whisper-french.mp3',
            output_file_path=output_file_path, output_format=OutputFormat.TXT,
            open_file_on_complete=False, word_level_timings=False)
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

        assert 'Bienvenue dans Passe-Relle, un podcast' in result['text']


def get_model_path(model_name: str, use_whisper_cpp: bool) -> str:
    model_loader = ModelLoader(model_name, use_whisper_cpp)
    model_path = ''

    def on_load_model(path: str):
        nonlocal model_path
        model_path = path

    model_loader.completed.connect(on_load_model)
    model_loader.run()
    return model_path


def call_counter(num_calls: int):
    """Returns a function that returns True when it has been
    called the given number of times.
    """
    count = 0

    def _call_counter(_):
        nonlocal count
        count += 1
        return count >= num_calls

    return _call_counter
