from transcriber import Transcriber


class TestTranscriber:
    def test_transcriber(self):
        def text_callback(text: str):
            pass

        transcriber = Transcriber(model=None, language='en',
                                  status_callback=text_callback, task=Transcriber.Task.TRANSCRIBE)
        assert transcriber != None
