
import os
import tempfile

from _whisper import Task, WhisperCpp
from transcriber import (FileTranscriber, RecordingTranscriber, Status,
                         to_timestamp)


class TestRecordingTranscriber:
    def test_transcriber(self):
        def text_callback(status: Status):
            pass

        transcriber = RecordingTranscriber(model=WhisperCpp('testdata/ggml-tiny.bin'), language='en',
                                           status_callback=text_callback, task=Task.TRANSCRIBE)
        assert transcriber != None


class TestFileTranscriber:
    def test_default_output_file(self):
        assert FileTranscriber.get_default_output_file_path(
            Task.TRANSLATE, '/a/b/c.txt').startswith('/a/b/c (Translated on ')

    def test_transcribe_whisper_cpp(self):
        output_file_path = os.path.join(tempfile.gettempdir(), 'whisper.txt')
        transcriber = FileTranscriber(
            model=WhisperCpp('testdata/ggml-tiny.bin'), language='en',
            task=Task.TRANSCRIBE, file_path='testdata/whisper.m4a',
            output_file_path=output_file_path,
            open_file_on_complete=False)
        transcriber.start()
        transcriber.join()

        assert os.path.isfile(output_file_path)


class TestToTimestamp:
    def test_to_timestamp(self):
        assert to_timestamp(0) == '00:00:00.000'
        assert to_timestamp(123456789) == '34:17:36.789'
