import os
import tempfile

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

    def test_transcribe_whisper(self):
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
            open_file_on_complete=False, event_callback=event_callback)
        transcriber.start()
        transcriber.join()

        assert os.path.isfile(output_file_path)

        output_file = open(output_file_path, 'r', encoding='utf-8')
        assert 'Bienvenue dans Passe-Relle, un podcast' in output_file.read()

        # Reports progress at 0, 0<progress<100, and 100
        assert len([event for event in events if isinstance(
            event, FileTranscriber.ProgressEvent) and event.current_value == 0 and event.max_value == 100]) > 0
        assert len([event for event in events if isinstance(
            event, FileTranscriber.ProgressEvent) and event.current_value == 100 and event.max_value == 100]) > 0
        assert len([event for event in events if isinstance(
            event, FileTranscriber.ProgressEvent) and event.current_value > 0 and event.current_value < 100 and event.max_value == 100]) > 0

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
            open_file_on_complete=False, event_callback=event_callback)
        transcriber.start()
        transcriber.join()

        assert os.path.isfile(output_file_path)

        output_file = open(output_file_path, 'r', encoding='utf-8')
        assert 'Bienvenue dans Passe-Relle, un podcast' in output_file.read()


class TestToTimestamp:
    def test_to_timestamp(self):
        assert to_timestamp(0) == '00:00:00.000'
        assert to_timestamp(123456789) == '34:17:36.789'
