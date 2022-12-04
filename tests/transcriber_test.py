import logging
import os
import pathlib
import tempfile
import time
from unittest.mock import Mock

import pytest

from buzz.model_loader import ModelLoader
from buzz.transcriber import (FileTranscriber, OutputFormat,
                              RecordingTranscriber, WhisperCppFileTranscriber,
                              to_timestamp)
from buzz.whispr import Task


def get_model_path(model_name: str, use_whisper_cpp: bool) -> str:
    model_loader = ModelLoader(model_name, use_whisper_cpp)
    model_path = ''

    def on_load_model(path: str):
        nonlocal model_path
        model_path = path

    model_loader.signals.completed.connect(on_load_model)
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
            model_path=model_path, language='fr',
            task=task, file_path='testdata/whisper-french.mp3',
            output_file_path=output_file_path.as_posix(), output_format=OutputFormat.TXT,
            open_file_on_complete=False,
            word_level_timings=False)
        mock_progress = Mock()
        with qtbot.waitSignal(transcriber.signals.completed, timeout=10000):
            transcriber.signals.progress.connect(mock_progress)
            transcriber.run()

        assert os.path.isfile(output_file_path)

        output_file = open(output_file_path, 'r', encoding='utf-8')
        assert output_text in output_file.read()

        mock_progress.assert_called()


class TestFileTranscriber:
    def test_default_output_file(self):
        srt = FileTranscriber.get_default_output_file_path(
            Task.TRANSLATE, '/a/b/c.mp4', OutputFormat.TXT)
        assert srt.startswith('/a/b/c (Translated on ')
        assert srt.endswith('.txt')

        srt = FileTranscriber.get_default_output_file_path(
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
    def test_transcribe_whisper(self, tmp_path: pathlib.Path, word_level_timings: bool, output_format: OutputFormat, output_text: str):
        output_file_path = tmp_path / f'whisper.{output_format.value.lower()}'

        events = []

        def event_callback(event: FileTranscriber.Event):
            events.append(event)

        model_path = get_model_path('tiny', False)
        transcriber = FileTranscriber(
            model_path=model_path, language='fr',
            task=Task.TRANSCRIBE, file_path='testdata/whisper-french.mp3',
            output_file_path=output_file_path.as_posix(), output_format=output_format,
            open_file_on_complete=False, event_callback=event_callback,
            word_level_timings=word_level_timings)
        transcriber.start()
        transcriber.join()

        assert os.path.isfile(output_file_path)

        output_file = open(output_file_path, 'r', encoding='utf-8')
        assert output_text in output_file.read()

        # Reports progress at 0, 0<progress<100, and 100
        assert len([event for event in events if isinstance(
            event, FileTranscriber.ProgressEvent) and event.current_value == 0 and event.max_value == 100]) > 0
        assert len([event for event in events if isinstance(
            event, FileTranscriber.ProgressEvent) and event.current_value == 100 and event.max_value == 100]) > 0
        assert len([event for event in events if isinstance(
            event, FileTranscriber.ProgressEvent) and event.current_value > 0 and event.current_value < 100 and event.max_value == 100]) > 0

    def test_transcribe_whisper_stop(self):
        output_file_path = os.path.join(tempfile.gettempdir(), 'whisper.txt')
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        events = []

        def event_callback(event: FileTranscriber.Event):
            events.append(event)

        model_path = get_model_path('tiny', False)
        transcriber = FileTranscriber(
            model_path=model_path, language='fr',
            task=Task.TRANSCRIBE, file_path='testdata/whisper-french.mp3',
            output_file_path=output_file_path, output_format=OutputFormat.TXT,
            open_file_on_complete=False, event_callback=event_callback,
            word_level_timings=False)
        transcriber.start()
        time.sleep(1)
        transcriber.stop()

        # Assert that file was not created
        assert os.path.isfile(output_file_path) is False


class TestToTimestamp:
    def test_to_timestamp(self):
        assert to_timestamp(0) == '00:00:00.000'
        assert to_timestamp(123456789) == '34:17:36.789'
