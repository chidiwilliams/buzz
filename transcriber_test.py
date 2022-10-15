
from transcriber import FileTranscriber, RecordingTranscriber, Status, Task


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
