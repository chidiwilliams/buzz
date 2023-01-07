import os
import time
from threading import Thread
from typing import Callable, Any
from unittest.mock import MagicMock

import numpy as np
import sounddevice
import whisper


class MockInputStream(MagicMock):
    running = False
    thread: Thread

    def __init__(self, callback: Callable[[np.ndarray, int, Any, sounddevice.CallbackFlags], None], *args, **kwargs):
        super().__init__(spec=sounddevice.InputStream)
        self.thread = Thread(target=self.target)
        self.callback = callback

    def start(self):
        self.thread.start()

    def target(self):
        sample_rate = whisper.audio.SAMPLE_RATE
        file_path = os.path.join(os.path.dirname(__file__), '../testdata/whisper-french.mp3')
        audio = whisper.load_audio(file_path, sr=sample_rate)

        chunk_duration_secs = 1

        self.running = True
        seek = 0
        num_samples_in_chunk = chunk_duration_secs * sample_rate

        while self.running:
            time.sleep(chunk_duration_secs)
            chunk = audio[seek:seek + num_samples_in_chunk]
            self.callback(chunk, 0, None, sounddevice.CallbackFlags())
            seek += num_samples_in_chunk

            # loop back around
            if seek + num_samples_in_chunk > audio.size:
                seek = 0

    def stop(self):
        self.running = False
        self.thread.join()

    def close(self):
        pass

    def __enter__(self):
        self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
