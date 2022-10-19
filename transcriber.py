import datetime
import enum
import logging
import os
import platform
import subprocess
from threading import Lock, Thread
from typing import Callable, Optional

import numpy as np
import sounddevice
import whisper

import _whisper


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

    def __init__(self, model: whisper.Whisper, language: Optional[str],
                 status_callback: Callable[[Status], None], task: Task,
                 input_device_index: Optional[int] = None) -> None:
        self.model = model
        self.current_stream = None
        self.status_callback = status_callback
        self.language = language
        self.task = task
        self.input_device_index = input_device_index
        self.sample_rate = self.get_device_sample_rate(
            device_id=input_device_index)
        self.n_batch_samples = 5 * self.sample_rate  # every 5 seconds
        # pause queueing if more than 3 batches behind
        self.max_queue_size = 3 * self.n_batch_samples
        self.queue = np.ndarray([], dtype=np.float32)
        self.mutex = Lock()
        self.text = ''

    def start_recording(self):
        logging.debug(
            f'Recording, language = {self.language}, task = {self.task}, device = {self.input_device_index}, sample rate = {self.sample_rate}')
        self.current_stream = sounddevice.InputStream(
            samplerate=self.sample_rate,
            blocksize=1 * self.sample_rate,  # 1 sec
            device=self.input_device_index, dtype="float32",
            channels=1, callback=self.stream_callback)
        self.current_stream.start()

        self.is_running = True

        self.current_thread = Thread(target=self.process_queue)
        self.current_thread.start()

    def process_queue(self):
        while self.is_running:
            self.mutex.acquire()
            if self.queue.size >= self.n_batch_samples:
                batch = self.queue[:self.n_batch_samples]
                self.queue = self.queue[self.n_batch_samples:]
                self.mutex.release()

                logging.debug(
                    f'Processing next frame, samples = {batch.size}, total samples = {self.queue.size}, amplitude = {self.amplitude(batch)}')
                self.status_callback(
                    Status(State.STARTING_NEXT_TRANSCRIPTION))
                time_started = datetime.datetime.now()

                result = self.model.transcribe(
                    audio=batch, language=self.language, task=self.task.value,
                    initial_prompt=self.text)  # prompt model with text from previous transcriptions
                batch_text: str = result.get('text')

                logging.debug(
                    f'Received next result, length = {len(batch_text)}, time taken = {datetime.datetime.now() - time_started}')
                self.status_callback(
                    Status(State.FINISHED_CURRENT_TRANSCRIPTION, batch_text))

                self.text += f'\n\n{batch_text}'
            else:
                self.mutex.release()

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
        chunk: np.ndarray = in_data.ravel()
        with self.mutex:
            if self.queue.size < self.max_queue_size:
                self.queue = np.append(self.queue, chunk)

    def amplitude(self, arr: np.ndarray):
        return (abs(max(arr)) + abs(min(arr))) / 2

    def stop_recording(self):
        if self.current_stream != None:
            self.current_stream.close()
            logging.debug('Closed recording stream')

        self.is_running = False

        if self.current_thread != None:
            logging.debug('Waiting for processing thread to terminate')
            self.current_thread.join()
            logging.debug('Processing thread terminated')


class FileTranscriber:
    """FileTranscriber transcribes an audio file to text, writes the text to a file, and then opens the file using the default program for opening txt files."""

    stopped = False

    def __init__(self, model: whisper.Whisper, language: Optional[str], task: Task, file_path: str, output_file_path: str, progress_callback: Callable[[int, int], None]) -> None:
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
        try:
            result = _whisper.transcribe(
                model=self.model, audio=self.file_path,
                progress_callback=self.progress_callback,
                language=self.language, task=self.task.value,
                check_stopped=self.check_stopped)
        except _whisper.Stopped:
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
