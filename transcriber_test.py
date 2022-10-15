
from transcriber import RecordingTranscriber, Status, Task


class TestRecordingTranscriber:
    def test_transcriber(self):
        def text_callback(status: Status):
            pass

        transcriber = RecordingTranscriber(model=None, language='en',
                                           status_callback=text_callback, task=Task.TRANSCRIBE)
        assert transcriber != None
