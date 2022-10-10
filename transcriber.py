import enum
import logging
import os
import queue
from threading import Thread
from typing import Callable, Optional

import numpy as np
import sounddevice
import whisper

import _whisper

# When the app is opened as a .app from Finder, the path doesn't contain /usr/local/bin
# which breaks the call to run `ffmpeg`. This sets the path manually to fix that.
os.environ["PATH"] += os.pathsep + "/usr/local/bin"


class Transcriber:
    """Transcriber records audio from a system microphone and transcribes it into text using Whisper."""

    class Task(enum.Enum):
        TRANSLATE = "translate"
        TRANSCRIBE = "transcribe"

    current_thread: Optional[Thread]
    current_stream: Optional[sounddevice.InputStream]
    is_running = False
    MAX_QUEUE_SIZE = 10

    def __init__(self, model: whisper.Whisper, language: Optional[str],
                 text_callback: Callable[[str], None], task: Task) -> None:
        self.model = model
        self.current_stream = None
        self.text_callback = text_callback
        self.language = language
        self.task = task
        self.queue: queue.Queue[np.ndarray] = queue.Queue(
            Transcriber.MAX_QUEUE_SIZE,
        )

    def start_recording(self, block_duration=10, input_device_index: Optional[int] = None):
        sample_rate = self.get_device_sample_rate(device_id=input_device_index)

        logging.debug("Recording... language: \"%s\", model: \"%s\", task: \"%s\", device: \"%s\", block duration: \"%s\", sample rate: \"%s\"" %
                      (self.language, self.model._get_name(), self.task, input_device_index, block_duration, sample_rate))
        self.current_stream = sounddevice.InputStream(
            samplerate=sample_rate,
            blocksize=block_duration * sample_rate,
            device=input_device_index, dtype="float32",
            channels=1, callback=self.stream_callback)
        self.current_stream.start()

        self.is_running = True

        self.current_thread = Thread(target=self.process_queue)
        self.current_thread.start()

    def process_queue(self):
        while self.is_running:
            try:
                block = self.queue.get(block=False)
                logging.debug(
                    'Processing next frame. Current queue size: %d' % self.queue.qsize())
                result = self.model.transcribe(
                    audio=block, language=self.language, task=self.task.value)
                logging.debug("Received next result: \"%s\"" % result["text"])
                self.text_callback(result["text"])  # type: ignore
            except queue.Empty:
                continue

    def get_device_sample_rate(self, device_id: Optional[int]) -> int:
        """Returns the sample rate to be used for recording. It uses the default sample rate
        provided by Whisper if the microphone supports it, or else it uses the device's default
        sample rate.
        """
        whisper_sample_rate = whisper.audio.SAMPLE_RATE
        try:
            sounddevice.check_input_settings(
                device=device_id, samplerate=whisper_sample_rate)
            return whisper_sample_rate
        except:
            device_info = sounddevice.query_devices(device=device_id)
            if isinstance(device_info, dict):
                return int(device_info.get('default_samplerate', whisper_sample_rate))
            return whisper_sample_rate

    def stream_callback(self, in_data, frame_count, time_info, status):
        # Try to enqueue the next block. If the queue is already full, drop the block.
        try:
            self.queue.put(in_data.ravel(), block=False)
        except queue.Full:
            return

    def stop_recording(self):
        if self.current_stream != None:
            self.current_stream.close()
            logging.debug('Closed recording stream')

        self.is_running = False
        self.queue.queue.clear()

        if self.current_thread != None:
            logging.debug('Waiting for processing thread to terminate')
            self.current_thread.join()
            logging.debug('Processing thread terminated')
