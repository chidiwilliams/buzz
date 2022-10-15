from transcriber import RecordingTranscriber


class TestTranscriber:
    def test_transcriber(self):
        def text_callback(text: str):
            pass

        transcriber = RecordingTranscriber(model=None, language='en',
                                  status_callback=text_callback, task=RecordingTranscriber.Task.TRANSCRIBE)
        assert transcriber != None
