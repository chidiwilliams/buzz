import datetime
import enum
import logging
import multiprocessing
import os
import platform
import select
import subprocess
import threading
from contextlib import contextmanager
from threading import Thread
from typing import Any, Callable, List, Optional, Union

import numpy as np
import sounddevice
import whisper

import _whisper
from _whisper import Segment


class State(enum.Enum):
    STARTING_NEXT_TRANSCRIPTION = 0
    FINISHED_CURRENT_TRANSCRIPTION = 1


class Status:
    def __init__(self, state: State, text='') -> None:
        self.state = state
        self.text = text


class RecordingTranscriber:
    """Transcriber records audio from a system microphone and transcribes it into text using Whisper."""

    current_thread: Optional[Thread]
    current_stream: Optional[sounddevice.InputStream]
    is_running = False
    MAX_QUEUE_SIZE = 10

    def __init__(self, model: Union[whisper.Whisper, _whisper.WhisperCpp], language: Optional[str],
                 status_callback: Callable[[Status], None], task: _whisper.Task,
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
        self.mutex = threading.Lock()
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
                samples = self.queue[:self.n_batch_samples]
                self.queue = self.queue[self.n_batch_samples:]
                self.mutex.release()

                logging.debug(
                    f'Processing next frame, samples = {samples.size}, total samples = {self.queue.size}, amplitude = {self.amplitude(samples)}')
                self.status_callback(
                    Status(State.STARTING_NEXT_TRANSCRIPTION))
                time_started = datetime.datetime.now()

                if isinstance(self.model, whisper.Whisper):
                    result = self.model.transcribe(
                        audio=samples, language=self.language, task=self.task.value,
                        initial_prompt=self.text)  # prompt model with text from previous transcriptions
                else:
                    result = self.model.transcribe(
                        audio=samples,
                        params=_whisper.whisper_cpp_params(
                            language=self.language if self.language is not None else 'en',
                            task=self.task.value))

                next_text: str = result.get('text')

                logging.debug(
                    f'Received next result, length = {len(next_text)}, time taken = {datetime.datetime.now() - time_started}')
                self.status_callback(
                    Status(State.FINISHED_CURRENT_TRANSCRIPTION, next_text))

                self.text += f'\n\n{next_text}'
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


def more_data(fd: int):
    r, _, _ = select.select([fd], [], [], 0)
    return bool(r)


def read_pipe_str(fd: int):
    out = b''
    while more_data(fd):
        out += os.read(fd, 1024)
    return out.decode('utf-8')


@contextmanager
def capture_fd(fd: int):
    """Captures and restores a file descriptor into a pipe

    Args:
        fd (int): file descriptor

    Yields:
        Tuple[int, int]: previous descriptor and pipe output
    """
    pipe_out, pipe_in = os.pipe()
    prev = os.dup(fd)
    os.dup2(pipe_in, fd)
    try:
        yield (prev, pipe_out)
    finally:
        os.dup2(prev, fd)


class OutputFormat(enum.Enum):
    TXT = 'txt'
    SRT = 'srt'
    VTT = 'vtt'


def to_timestamp(ms: float) -> str:
    hr = int(ms / (1000*60*60))
    ms = ms - hr * (1000*60*60)
    min = int(ms / (1000*60))
    ms = ms - min * (1000*60)
    sec = int(ms / 1000)
    ms = int(ms - sec * 1000)
    return f'{hr:02d}:{min:02d}:{sec:02d}.{ms:03d}'


def write_output(path: str, segments: List[Segment], should_open: bool, output_format: OutputFormat):
    file = open(path, 'w')

    if output_format == OutputFormat.TXT:
        for segment in segments:
            file.write(segment.text)

    elif output_format == OutputFormat.VTT:
        file.write('WEBVTT\n\n')
        for segment in segments:
            file.write(
                f'{to_timestamp(segment.start)} --> {to_timestamp(segment.end)}\n')
            file.write(f'{segment.text}\n\n')

    elif output_format == OutputFormat.SRT:
        for (i, segment) in enumerate(segments):
            file.write(f'{i+1}\n')
            file.write(
                f'{to_timestamp(segment.start)} --> {to_timestamp(segment.end)}\n')
            file.write(f'{segment.text}\n\n')

    file.close()

    if should_open:
        try:
            os.startfile(path)
        except AttributeError:
            opener = "open" if platform.system() == "Darwin" else "xdg-open"
            subprocess.call([opener, path])


def transcribe_cpp(
        model: _whisper.WhisperCpp, audio: Union[np.ndarray, str],
        params: Any, output_file_path: str, open_file_on_complete: bool, output_format):
    result = model.transcribe(audio=audio, params=params)
    write_output(output_file_path, result.get(
        'segments'), open_file_on_complete, output_format)


class FileTranscriber:
    """FileTranscriber transcribes an audio file to text, writes the text to a file, and then opens the file using the default program for opening txt files."""

    stopped = False

    def __init__(
            self, model: Union[whisper.Whisper, _whisper.WhisperCpp], language: Optional[str],
            task: _whisper.Task, file_path: str,
            output_file_path: str, output_format: OutputFormat,
            progress_callback: Callable[[int, int], None] = lambda *_: None,
            open_file_on_complete=True) -> None:
        self.model = model
        self.file_path = file_path
        self.output_file_path = output_file_path
        self.progress_callback = progress_callback
        self.language = language
        self.task = task
        self.open_file_on_complete = open_file_on_complete

        _, extension = os.path.splitext(self.output_file_path)
        self.output_format = output_format

    def start(self):
        self.current_thread = Thread(target=self.transcribe)
        self.current_thread.start()

    def transcribe(self):
        try:
            if isinstance(self.model, _whisper. WhisperCpp):
                self.progress_callback(0, 100)

                with capture_fd(2) as (_, stderr):
                    process = multiprocessing.Process(
                        target=transcribe_cpp,
                        args=(
                            self.model, self.file_path,
                            _whisper.whisper_cpp_params(
                                language=self.language if self.language is not None else 'en',
                                task=self.task, print_realtime=True, print_progress=True),
                            self.output_file_path,
                            self.open_file_on_complete,
                            self.output_format))
                    process.start()

                    while process.is_alive():
                        if self.check_stopped():
                            process.kill()

                        next_stderr = read_pipe_str(stderr)
                        if len(next_stderr) > 0:
                            progress = _whisper.whisper_cpp_progress(
                                next_stderr)
                            if progress != None:
                                self.progress_callback(progress, 100)

                self.progress_callback(100, 100)
            else:
                result = _whisper.transcribe(
                    model=self.model, audio=self.file_path,
                    progress_callback=self.progress_callback,
                    language=self.language, task=self.task.value,
                    check_stopped=self.check_stopped)

                segments = map(
                    lambda segment: Segment(
                        start=segment.get('start')*1000,  # s to ms
                        end=segment.get('end')*1000,      # s to ms
                        text=segment.get('text')),
                    result.get('segments'))

                write_output(self.output_file_path, list(
                    segments), self.open_file_on_complete, self.output_format)
        except _whisper.Stopped:
            return

    def join(self):
        self.current_thread.join()

    def stop(self):
        self.stopped = True

    def check_stopped(self):
        return self.stopped

    @classmethod
    def get_default_output_file_path(cls, task: _whisper.Task, input_file_path: str, output_format: OutputFormat):
        return f'{os.path.splitext(input_file_path)[0]} ({task.value.title()}d on {datetime.datetime.now():%d-%b-%Y %H-%M-%S}).{output_format.value}'
