import enum
import logging
import os
import queue
from typing import Callable, Optional

import numpy as np
import sounddevice
import whisper

# When the app is opened as a .app from Finder, the path doesn't contain /usr/local/bin
# which breaks the call to run `ffmpeg`. This sets the path manually to fix that.
os.environ["PATH"] += os.pathsep + "/usr/local/bin"


class Transcriber:
    """Transcriber records audio from a system microphone and transcribes it into text using Whisper."""

    class Task(enum.Enum):
        TRANSLATE = "translate"
        TRANSCRIBE = "transcribe"

    def __init__(self, model_name: str, language: Optional[str],
                 text_callback: Callable[[str], None], task: Task) -> None:
        self.model_name = model_name
        self.model = whisper.load_model(model_name)
        self.stream = None
        self.text_callback = text_callback
        self.language = language
        self.task = task
        self.queue: queue.Queue[np.ndarray] = queue.Queue()

    def start_recording(self, num_block=160, input_device_index: Optional[int] = None):
        logging.debug("Recording... language \"%s\", model \"%s\", task \"%s\", device \"%s\"" %
                      (self.language, self.model_name, self.task, input_device_index))

        self.stream = sounddevice.InputStream(
            samplerate=whisper.audio.SAMPLE_RATE, blocksize=whisper.audio.N_FRAMES*num_block,
            device=input_device_index, dtype="float32", channels=1,
            callback=self.stream_callback)
        self.stream.start()

        while True:
            chunk = self.queue.get()
            logging.debug(
                'Processing next frame. Current queue size: %d' % self.queue.qsize())
            result = self.model.transcribe(
                audio=chunk, language=self.language, task=self.task)
            logging.debug("Received next result: \"%s\"" % result["text"])
            self.text_callback(result["text"])

    def stream_callback(self, in_data, frame_count, time_info, status):
        self.queue.put(in_data.ravel())

    def stop_recording(self):
        if self.stream != None:
            logging.debug("Ending recording...")
            self.stream.close()
