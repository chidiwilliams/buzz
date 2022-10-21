
import os
import tempfile

from transcriber import (FileTranscriber, RecordingTranscriber, Status, Task,
                         WhisperCpp)


class TestRecordingTranscriber:
    def test_transcriber(self):
        def text_callback(status: Status):
            pass

        transcriber = RecordingTranscriber(model=None, language='en',
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
            output_file_path=output_file_path)
        transcriber.start()
        transcriber.join()

        assert os.path.isfile(output_file_path)
