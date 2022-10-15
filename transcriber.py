import datetime
import enum
import logging
import os
import platform
import queue
import subprocess
from threading import Thread
from typing import Callable, Optional

import numpy as np
import sounddevice
import whisper

import _whisper

# When the app is opened as a .app from Finder, the path doesn't contain /usr/local/bin
# which breaks the call to run `ffmpeg`. This sets the path manually to fix that.
os.environ["PATH"] += os.pathsep + "/usr/local/bin"


class State(enum.Enum):
    STARTING_NEXT_TRANSCRIPTION = 0
    FINISHED_CURRENT_TRANSCRIPTION = 1


class Status:
    def __init__(self, state: State, text='') -> None:
        self.state = state
        self.text = text


class Task(enum.Enum):
    TRANSLATE = "translate"
    TRANSCRIBE = "transcribe"


class RecordingTranscriber:
    """Transcriber records audio from a system microphone and transcribes it into text using Whisper."""

    current_thread: Optional[Thread]
    current_stream: Optional[sounddevice.InputStream]
    is_running = False
    MAX_QUEUE_SIZE = 10

    def __init__(self, model: whisper.Whisper, language: Optional[str],
                 status_callback: Callable[[Status], None], task: Task) -> None:
        self.model = model
        self.current_stream = None
        self.status_callback = status_callback
        self.language = language
        self.task = task
        self.queue: queue.Queue[np.ndarray] = queue.Queue(
            RecordingTranscriber.MAX_QUEUE_SIZE,
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
                self.status_callback(Status(State.STARTING_NEXT_TRANSCRIPTION))
                result = self.model.transcribe(
                    audio=block, language=self.language, task=self.task.value)
                text = result.get("text")
                logging.debug(
                    "Received next result of length: %s" % len(text))
                self.status_callback(
                    Status(State.FINISHED_CURRENT_TRANSCRIPTION, text))
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
            chunk = in_data.ravel()
            logging.debug('Received next chunk: length %s, amplitude %s, status "%s"'
                          % (len(chunk), (abs(max(chunk)) + abs(min(chunk))) / 2, status))
            self.queue.put(chunk, block=False)
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


class FileTranscriber:
    """FileTranscriber transcribes an audio file to text, writes the text to a file, and then opens the file using the default program for opening txt files."""

    stopped = False

    def __init__(self, model: whisper.Whisper, language: str, task: Task, file_path: str, output_file_path: str, progress_callback: Callable[[int, int], None]) -> None:
        self.model = model
        self.file_path = file_path
        self.output_file_path = output_file_path
        self.progress_callback = progress_callback
        self.language = language
        self.task = task

    def start(self):
        self.current_thread = Thread(target=self.transcribe)
        self.current_thread.start()

    def transcribe(self):
        result = _whisper.transcribe(model=self.model, audio=self.file_path,
                                     progress_callback=self.progress_callback,
                                     language=self.language, task=self.task.value,
                                     check_stopped=self.check_stopped)

        # If the stop signal was received, return
        if result == None:
            return

        output_file = open(self.output_file_path, 'w')
        output_file.write(result.get('text'))
        output_file.close()

        try:
            os.startfile(self.output_file_path)
        except AttributeError:
            opener = "open" if platform.system() == "Darwin" else "xdg-open"
            subprocess.call([opener, self.output_file_path])

    def stop(self):
        self.stopped = True

    def check_stopped(self):
        return self.stopped

    @classmethod
    def get_default_output_file_path(cls, task: Task, input_file_path: str):
        return f'{os.path.splitext(input_file_path)[0]} ({task.value.title()}d on {datetime.datetime.now():%d-%b-%Y %H-%M-%S}).txt'
