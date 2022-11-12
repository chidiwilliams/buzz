import os
import pathlib
import tempfile

import pytest

from transcriber import (FileTranscriber, OutputFormat, RecordingTranscriber,
                         to_timestamp)
from whispr import Task


class TestRecordingTranscriber:
    def test_transcriber(self):

        transcriber = RecordingTranscriber(
            model_name='tiny', use_whisper_cpp=True, language='en',
            task=Task.TRANSCRIBE)
        assert transcriber is not None


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
            (True, OutputFormat.SRT, '1\n00:00:00.040 --> 00:00:00.059\n Bienvenue\n\n2\n00:00:00.059 --> 00:00:00.359\n dans P'),
        ])
    def test_transcribe_whisper(self, tmp_path: pathlib.Path, word_level_timings: bool, output_format: OutputFormat, output_text: str):
        output_file_path = tmp_path / f'whisper.{output_format.value.lower()}'

        events = []

        def event_callback(event: FileTranscriber.Event):
            events.append(event)

        transcriber = FileTranscriber(
            model_name='tiny', use_whisper_cpp=False, language='fr',
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

        transcriber = FileTranscriber(
            model_name='tiny', use_whisper_cpp=False, language='fr',
            task=Task.TRANSCRIBE, file_path='testdata/whisper-french.mp3',
            output_file_path=output_file_path, output_format=OutputFormat.TXT,
            open_file_on_complete=False, event_callback=event_callback,
            word_level_timings=False)
        transcriber.start()
        transcriber.stop()

        # Assert that file was not created and there was no completed progress event
        assert os.path.isfile(output_file_path) is False
        assert any([isinstance(event, FileTranscriber.ProgressEvent)
                   and event.current_value == event.max_value for event in events]) is False

    def test_transcribe_whisper_cpp(self):
        output_file_path = os.path.join(
            tempfile.gettempdir(), 'whisper_cpp.txt')
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        events = []

        def event_callback(event: FileTranscriber.Event):
            events.append(event)

        transcriber = FileTranscriber(
            model_name='tiny', use_whisper_cpp=True, language='fr',
            task=Task.TRANSCRIBE, file_path='testdata/whisper-french.mp3',
            output_file_path=output_file_path, output_format=OutputFormat.TXT,
            open_file_on_complete=False, event_callback=event_callback,
            word_level_timings=False)
        transcriber.start()
        transcriber.join()

        assert os.path.isfile(output_file_path)

        output_file = open(output_file_path, 'r', encoding='utf-8')
        assert 'Bienvenue dans Passe-Relle, un podcast' in output_file.read()


class TestToTimestamp:
    def test_to_timestamp(self):
        assert to_timestamp(0) == '00:00:00.000'
        assert to_timestamp(123456789) == '34:17:36.789'
