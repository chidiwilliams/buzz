import datetime
import enum
import logging
import multiprocessing
import os
import platform
import subprocess
import threading
import typing
from dataclasses import dataclass
from multiprocessing.connection import Connection
from threading import Thread
from typing import Callable, List, Optional

import numpy as np
import sounddevice
import whisper
from sounddevice import PortAudioError

from conn import pipe_stderr, pipe_stdout
from stable_ts.stable_whisper import group_word_timestamps, modify_model
from whispr import (ModelLoader, Segment, Stopped, Task, WhisperCpp,
                    read_progress, whisper_cpp_params)


class RecordingTranscriber:
    """Transcriber records audio from a system microphone and transcribes it into text using Whisper."""

    current_thread: Optional[Thread]
    current_stream: Optional[sounddevice.InputStream]
    is_running = False
    MAX_QUEUE_SIZE = 10

    class Event:
        pass

    class LoadedModelEvent(Event):
        pass

    @dataclass
    class TranscribedNextChunkEvent(Event):
        text: str

    def __init__(self,
                 model_name: str, use_whisper_cpp: bool,
                 language: Optional[str], task: Task,
                 on_download_model_chunk: Callable[[
                     int, int], None] = lambda *_: None,
                 event_callback: Callable[[Event], None] = lambda *_: None,
                 input_device_index: Optional[int] = None) -> None:
        self.current_stream = None
        self.event_callback = event_callback
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
        self.on_download_model_chunk = on_download_model_chunk
        self.model_loader = ModelLoader(
            name=model_name, use_whisper_cpp=use_whisper_cpp,)

    def start_recording(self):
        self.current_thread = Thread(target=self.process_queue)
        self.current_thread.start()

    def process_queue(self):
        try:
            model = self.model_loader.load(
                on_download_model_chunk=self.on_download_model_chunk)
        except Stopped:
            return

        self.event_callback(self.LoadedModelEvent())

        logging.debug('Recording, language = %s, task = %s, device = %s, sample rate = %s',
                      self.language, self.task, self.input_device_index, self.sample_rate)
        self.current_stream = sounddevice.InputStream(
            samplerate=self.sample_rate,
            blocksize=1 * self.sample_rate,  # 1 sec
            device=self.input_device_index, dtype="float32",
            channels=1, callback=self.stream_callback)
        self.current_stream.start()

        self.is_running = True

        while self.is_running:
            self.mutex.acquire()
            if self.queue.size >= self.n_batch_samples:
                samples = self.queue[:self.n_batch_samples]
                self.queue = self.queue[self.n_batch_samples:]
                self.mutex.release()

                logging.debug('Processing next frame, sample size = %s, queue size = %s, amplitude = %s',
                              samples.size, self.queue.size, self.amplitude(samples))
                time_started = datetime.datetime.now()

                if isinstance(model, whisper.Whisper):
                    result = model.transcribe(
                        audio=samples, language=self.language, task=self.task.value,
                        initial_prompt=self.text)  # prompt model with text from previous transcriptions
                else:
                    result = model.transcribe(
                        audio=samples,
                        params=whisper_cpp_params(
                            language=self.language if self.language is not None else 'en',
                            task=self.task.value, word_level_timings=False))

                next_text: str = result.get('text')

                logging.debug('Received next result, length = %s, time taken = %s',
                              len(next_text), datetime.datetime.now()-time_started)
                self.event_callback(self.TranscribedNextChunkEvent(next_text))

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
        except PortAudioError:
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
        if self.is_running:
            self.is_running = False

            if self.current_stream is not None:
                self.current_stream.close()
                logging.debug('Closed recording stream')

            if self.current_thread is not None:
                logging.debug('Waiting for recording thread to terminate')
                self.current_thread.join()
                logging.debug('Recording thread terminated')

    def stop_loading_model(self):
        self.model_loader.stop()


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
    file = open(path, 'w', encoding='utf-8')

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


class FileTranscriber:
    """FileTranscriber transcribes an audio file to text, writes the text to a file, and then opens the file using the default program for opening txt files."""

    stopped = False
    current_thread: Optional[Thread] = None
    current_process: Optional[multiprocessing.Process] = None

    class Event():
        pass

    @dataclass
    class ProgressEvent(Event):
        current_value: int
        max_value: int

    class LoadedModelEvent(Event):
        pass

    class CompletedTranscriptionEvent(Event):
        pass

    def __init__(
            self,
            model_name: str, use_whisper_cpp: bool,
            language: Optional[str], task: Task, file_path: str,
            output_file_path: str, output_format: OutputFormat,
            word_level_timings: bool,
            event_callback: Callable[[Event], None] = lambda *_: None,
            on_download_model_chunk: Callable[[
                int, int], None] = lambda *_: None,
            open_file_on_complete=True) -> None:
        self.file_path = file_path
        self.output_file_path = output_file_path
        self.language = language
        self.task = task
        self.open_file_on_complete = open_file_on_complete
        self.output_format = output_format
        self.word_level_timings = word_level_timings

        self.model_name = model_name
        self.use_whisper_cpp = use_whisper_cpp
        self.on_download_model_chunk = on_download_model_chunk

        self.model_loader = ModelLoader(self.model_name, self.use_whisper_cpp)
        self.event_callback = event_callback

    def start(self):
        self.current_thread = Thread(target=self.transcribe, args=())
        self.current_thread.start()

    def transcribe(self):
        if self.stopped:
            return

        try:
            model_path = self.model_loader.get_model_path(
                on_download_model_chunk=self.on_download_model_chunk)
        except Stopped:
            return

        self.event_callback(self.LoadedModelEvent())

        time_started = datetime.datetime.now()
        logging.debug(
            'Starting file transcription, file path = %s, language = %s, task = %s, output file path = %s, output format = %s, model_path = %s',
            self.file_path, self.language, self.task, self.output_file_path, self.output_format, model_path)

        recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)

        if self.stopped:
            return

        self.event_callback(self.ProgressEvent(0, 100))
        if self.use_whisper_cpp:
            self.current_process = multiprocessing.Process(
                target=transcribe_whisper_cpp,
                args=(
                    send_pipe, model_path, self.file_path,
                    self.output_file_path, self.open_file_on_complete,
                    self.output_format,
                    self.language if self.language is not None else 'en',
                    self.task, True, True,
                    self.word_level_timings
                ))
        else:
            self.current_process = multiprocessing.Process(
                target=transcribe_whisper,
                args=(
                    send_pipe, model_path, self.file_path,
                    self.language, self.task, self.output_file_path,
                    self.open_file_on_complete, self.output_format,
                    self.word_level_timings
                ))

        self.current_process.start()

        thread = Thread(target=read_progress, args=(
            recv_pipe, self.use_whisper_cpp,
            lambda current_value, max_value: self.event_callback(self.ProgressEvent(current_value, max_value))))
        thread.start()

        self.current_process.join()
        self.current_process.close()
        self.stopped = True

        recv_pipe.close()
        send_pipe.close()

        self.event_callback(self.ProgressEvent(100, 100))
        self.event_callback(self.CompletedTranscriptionEvent())
        logging.debug('Completed file transcription, time taken = %s',
                      datetime.datetime.now()-time_started)

    def stop_loading_model(self):
        self.model_loader.stop()

    def join(self):
        if self.current_thread is not None:
            self.current_thread.join()

    def stop(self):
        if self.stopped is False:
            self.stopped = True

            self.model_loader.stop()

            if self.current_process is not None and self.current_process.is_alive():
                self.current_process.terminate()
                logging.debug('File transcription process terminated')

            if self.current_thread is not None and self.current_thread.is_alive():
                logging.debug(
                    'Waiting for file transcription thread to terminate')
                self.current_thread.join()
                logging.debug('File transcription thread terminated')

            self.current_process = None

    @classmethod
    def get_default_output_file_path(cls, task: Task, input_file_path: str, output_format: OutputFormat):
        return f'{os.path.splitext(input_file_path)[0]} ({task.value.title()}d on {datetime.datetime.now():%d-%b-%Y %H-%M-%S}).{output_format.value}'


def transcribe_whisper(
        stderr_conn: Connection, model_path: str, file_path: str,
        language: Optional[str], task: Task, output_file_path: str,
        open_file_on_complete: bool, output_format: OutputFormat,
        word_level_timings: bool):
    with pipe_stderr(stderr_conn):
        model = whisper.load_model(model_path)

        if word_level_timings:
            modify_model(model)

        result = model.transcribe(
            audio=file_path, language=language, task=task.value, verbose=False)

        whisper_segments = group_word_timestamps(
            result) if word_level_timings else result.get('segments')

        segments = map(
            lambda segment: Segment(
                start=segment.get('start')*1000,  # s to ms
                end=segment.get('end')*1000,      # s to ms
                text=segment.get('text')),
            whisper_segments)

        write_output(output_file_path, list(
            segments), open_file_on_complete, output_format)


def transcribe_whisper_cpp(
        stderr_conn: Connection, model_path: str, audio: typing.Union[np.ndarray, str],
        output_file_path: str, open_file_on_complete: bool, output_format: OutputFormat,
        language: str, task: Task, print_realtime: bool, print_progress: bool,
        word_level_timings: bool):
    # TODO: capturing output does not work because ctypes functions
    # See: https://stackoverflow.com/questions/9488560/capturing-print-output-from-shared-library-called-from-python-with-ctypes-module
    with pipe_stdout(stderr_conn), pipe_stderr(stderr_conn):
        model = WhisperCpp(model_path)
        params = whisper_cpp_params(
            language, task, word_level_timings, print_realtime, print_progress)
        result = model.transcribe(audio=audio, params=params)
        segments: List[Segment] = result.get('segments')
        write_output(
            output_file_path, segments, open_file_on_complete, output_format)
