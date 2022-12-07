import time
from unittest.mock import Mock

import whisper
from threading import Thread


def load_mock_input_stream(audio_path: str):
    class MockInputStream:
        """Mock implementation of sounddevice.InputStream
        """

        def __init__(self, blocksize: int, samplerate: int, callback, **args) -> None:
            self.callback = callback
            self.blocksize = blocksize
            self.samplerate = samplerate
            self.args = args

            self.audio = whisper.audio.load_audio(audio_path)
            self.thread = Thread(target=self.run_stream)
            self.stopped = False

        def start(self):
            self.thread.start()

        def run_stream(self):
            timeout = self.blocksize / self.samplerate

            current = 0
            while current < self.audio.size and self.stopped is False:
                time.sleep(timeout)

                next_chunk = Mock()
                next_chunk.ravel = Mock()
                next_chunk.ravel.return_value = self.audio[current:current+self.blocksize]

                self.callback(next_chunk, None, None, None)

                current = current + self.blocksize

        def close(self):
            self.stopped = True
            self.thread.join()

    return MockInputStream
