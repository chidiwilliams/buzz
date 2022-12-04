import datetime
import enum
import logging
import multiprocessing
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from multiprocessing.connection import Connection
from threading import Thread
from typing import Callable, List, Optional, Tuple

import ffmpeg
import numpy as np
import sounddevice
import stable_whisper
import whisper
from PyQt6.QtCore import QObject, QProcess, QRunnable, pyqtSignal, pyqtSlot
from sounddevice import PortAudioError

from .conn import pipe_stderr
from .whispr import (Segment, Task, WhisperCpp, read_progress,
                     whisper_cpp_params)


class RecordingTranscriber:
    """Transcriber records audio from a system microphone and transcribes it into text using Whisper."""

    current_thread: Optional[Thread]
    current_stream: Optional[sounddevice.InputStream]
    is_running = False
    MAX_QUEUE_SIZE = 10

    class Event:
        pass

    @dataclass
    class TranscribedNextChunkEvent(Event):
        text: str

    def __init__(self,
                 model_path: str, use_whisper_cpp: bool,
                 language: Optional[str], task: Task,
                 on_download_model_chunk: Callable[[
                     int, int], None] = lambda *_: None,
                 event_callback: Callable[[Event], None] = lambda *_: None,
                 input_device_index: Optional[int] = None) -> None:
        self.model_path = model_path
        self.use_whisper_cpp = use_whisper_cpp
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

    def start_recording(self):
        self.current_thread = Thread(target=self.process_queue)
        self.current_thread.start()

    def process_queue(self):
        model = WhisperCpp(
            self.model_path) if self.use_whisper_cpp else whisper.load_model(self.model_path)

        logging.debug(
            'Recording, language = %s, task = %s, device = %s, sample rate = %s, model_path = %s',
            self.language, self.task, self.input_device_index, self.sample_rate, self.model_path)
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
    logging.debug(
        'Writing transcription output, path = %s, output format = %s, number of segments = %s', path, output_format, len(segments))

    with open(path, 'w', encoding='utf-8') as file:
        if output_format == OutputFormat.TXT:
            for segment in segments:
                file.write(segment.text + ' ')

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

    if should_open:
        try:
            os.startfile(path)
        except AttributeError:
            opener = "open" if platform.system() == "Darwin" else "xdg-open"
            subprocess.call([opener, path])


class WhisperCppFileTranscriber(QRunnable):
    class Signals(QObject):
        progress = pyqtSignal(tuple)  # (current, total)
        completed = pyqtSignal(bool)
        error = pyqtSignal(str)

    signals: Signals
    duration_audio_ms = sys.maxsize  # max int
    segments: List[Segment] = []

    def __init__(
            self,
            model_path: str, language: Optional[str], task: Task, file_path: str,
            output_file_path: str, output_format: OutputFormat,
            word_level_timings: bool, open_file_on_complete=True,
    ) -> None:
        super(WhisperCppFileTranscriber, self).__init__()

        self.file_path = file_path
        self.output_file_path = output_file_path
        self.language = language
        self.task = task
        self.open_file_on_complete = open_file_on_complete
        self.output_format = output_format
        self.word_level_timings = word_level_timings
        self.model_path = model_path
        self.signals = self.Signals()

        self.process = QProcess()
        self.process.readyReadStandardError.connect(self.read_std_err)
        self.process.readyReadStandardOutput.connect(self.read_std_out)
        self.process.finished.connect(self.on_process_finished)

    @pyqtSlot()
    def run(self):
        logging.debug(
            'Starting file transcription, file path = %s, language = %s, task = %s, output file path = %s, output format = %s, model_path = %s',
            self.file_path, self.language, self.task, self.output_file_path, self.output_format, self.model_path)

        wav_file = tempfile.mktemp()+'.wav'
        (
            ffmpeg.input(self.file_path)
            .output(wav_file, acodec="pcm_s16le", ac=1, ar=whisper.audio.SAMPLE_RATE)
            .run(cmd=["ffmpeg", "-nostdin"], capture_stdout=True, capture_stderr=True)
        )

        args = [
            '--language', self.language if self.language is not None else 'en',
            '--max-len', '1' if self.word_level_timings else '0',
            '--model', self.model_path,
            '--verbose'
        ]
        if self.task == Task.TRANSLATE:
            args.append('--translate')
        args.append(wav_file)

        logging.debug('Running whisper_cpp process, args = %s', args)

        self.process.start('./whisper_cpp', args)

    def on_process_finished(self):
        status = self.process.exitStatus()
        logging.debug('whisper_cpp process completed with status = %s', status)
        if status == QProcess.ExitStatus.NormalExit:
            self.signals.progress.emit(
                (self.duration_audio_ms, self.duration_audio_ms))
            write_output(
                self.output_file_path, self.segments, self.open_file_on_complete, self.output_format)

        self.signals.completed.emit(True)

    def stop(self):
        process_state = self.process.state()
        if process_state == QProcess.ProcessState.Starting or process_state == QProcess.ProcessState.Running:
            self.process.terminate()

    def read_std_out(self):
        output = self.process.readAllStandardOutput().data().decode('UTF-8').strip()

        if len(output) > 0:
            lines = output.split('\n')
            for line in lines:
                timings, text = line.split('  ')
                start, end = self.parse_timings(timings)
                segment = Segment(start, end, text.strip())
                self.segments.append(segment)
                self.signals.progress.emit((end, self.duration_audio_ms))

    def parse_timings(self, timings: str) -> Tuple[int, int]:
        start, end = timings[1:len(timings)-1].split(' --> ')
        return self.parse_timestamp(start), self.parse_timestamp(end)

    def parse_timestamp(self, timestamp: str) -> int:
        hrs, mins, secs_ms = timestamp.split(':')
        secs, ms = secs_ms.split('.')
        return int(hrs)*60*60*1000 + int(mins)*60*1000 + int(secs)*1000 + int(ms)

    def read_std_err(self):
        output = self.process.readAllStandardError().data().decode('UTF-8').strip()
        logging.debug('whisper_cpp (stderr): %s', output)

        lines = output.split('\n')
        for line in lines:
            if line.startswith('main: processing'):
                match = re.search(r'samples, (.*) sec', line)
                if match is not None:
                    self.duration_audio_ms = round(float(match.group(1))*1000)


class FileTranscriber:
    """FileTranscriber transcribes an audio file to text, writes the text to a file, and then opens the file using the default program for opening txt files."""

    stopped = False
    current_thread: Optional[Thread] = None
    current_process: Optional[multiprocessing.Process] = None
    SUPPORTED_FILE_FORMATS = 'Audio files (*.mp3 *.wav *.m4a *.ogg);;Video files (*.mp4 *.webm *.ogm *.mov);;All files (*.*)'

    class Event():
        pass

    @dataclass
    class ProgressEvent(Event):
        current_value: int
        max_value: int

    class CompletedTranscriptionEvent(Event):
        pass

    def __init__(
            self,
            model_path: str, language: Optional[str], task: Task, file_path: str,
            output_file_path: str, output_format: OutputFormat,
            word_level_timings: bool,
            event_callback: Callable[[Event], None] = lambda *_: None,
            open_file_on_complete=True) -> None:
        self.file_path = file_path
        self.output_file_path = output_file_path
        self.language = language
        self.task = task
        self.open_file_on_complete = open_file_on_complete
        self.output_format = output_format
        self.word_level_timings = word_level_timings
        self.model_path = model_path
        self.event_callback = event_callback

    def start(self):
        self.current_thread = Thread(target=self.transcribe, args=())
        self.current_thread.start()

    def transcribe(self):
        time_started = datetime.datetime.now()
        logging.debug(
            'Starting file transcription, file path = %s, language = %s, task = %s, output file path = %s, output format = %s, model_path = %s',
            self.file_path, self.language, self.task, self.output_file_path, self.output_format, self.model_path)

        recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)

        if self.stopped:
            return

        self.event_callback(self.ProgressEvent(0, 100))
        self.current_process = multiprocessing.Process(
            target=transcribe_whisper,
            args=(
                send_pipe, self.model_path, self.file_path,
                self.language, self.task, self.output_file_path,
                self.open_file_on_complete, self.output_format,
                self.word_level_timings
            ))

        self.current_process.start()

        thread = Thread(target=read_progress, args=(
            recv_pipe,
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

    def join(self):
        if self.current_thread is not None:
            self.current_thread.join()

    def stop(self):
        if self.stopped is False:
            self.stopped = True

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
            stable_whisper.modify_model(model)
            result = model.transcribe(
                audio=file_path, language=language, task=task.value, pbar=True)
        else:
            result = model.transcribe(
                audio=file_path, language=language, task=task.value, verbose=False)

        whisper_segments = stable_whisper.group_word_timestamps(
            result) if word_level_timings else result.get('segments')

        segments = map(
            lambda segment: Segment(
                start=segment.get('start')*1000,  # s to ms
                end=segment.get('end')*1000,      # s to ms
                text=segment.get('text')),
            whisper_segments)

        write_output(output_file_path, list(
            segments), open_file_on_complete, output_format)
