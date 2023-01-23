import ctypes
import datetime
import enum
import json
import logging
import multiprocessing
import os
import platform
import queue
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from multiprocessing.connection import Connection
from random import randint
from threading import Thread
from typing import Any, List, Optional, Tuple, Union

import ffmpeg
import numpy as np
import sounddevice
import stable_whisper
import whisper
from PyQt6.QtCore import QObject, QProcess, pyqtSignal, pyqtSlot, QThread
from sounddevice import PortAudioError

from . import transformers_whisper
from .conn import pipe_stderr
from .model_loader import TranscriptionModel, ModelType
from .transformers_whisper import TransformersWhisper

# Catch exception from whisper.dll not getting loaded.
# TODO: Remove flag and try-except when issue with loading
# the DLL in some envs is fixed.
LOADED_WHISPER_DLL = False
try:
    import buzz.whisper_cpp as whisper_cpp

    LOADED_WHISPER_DLL = True
except ImportError:
    logging.exception('')

DEFAULT_WHISPER_TEMPERATURE = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


class Task(enum.Enum):
    TRANSLATE = "translate"
    TRANSCRIBE = "transcribe"


@dataclass
class Segment:
    start: int  # start time in ms
    end: int  # end time in ms
    text: str


@dataclass()
class TranscriptionOptions:
    language: Optional[str] = None
    task: Task = Task.TRANSCRIBE
    model: TranscriptionModel = TranscriptionModel()
    word_level_timings: bool = False
    temperature: Tuple[float, ...] = DEFAULT_WHISPER_TEMPERATURE
    initial_prompt: str = ''


@dataclass()
class FileTranscriptionOptions:
    file_paths: List[str]


@dataclass
class FileTranscriptionTask:
    class Status(enum.Enum):
        QUEUED = 'queued'
        IN_PROGRESS = 'in_progress'
        COMPLETED = 'completed'
        FAILED = 'failed'
        CANCELED = 'canceled'

    file_path: str
    transcription_options: TranscriptionOptions
    file_transcription_options: FileTranscriptionOptions
    model_path: str
    id: int = field(default_factory=lambda: randint(0, 1_000_000))
    segments: List[Segment] = field(default_factory=list)
    status: Optional[Status] = None
    fraction_completed = 0.0
    error: Optional[str] = None


class RecordingTranscriber(QObject):
    transcription = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    is_running = False
    MAX_QUEUE_SIZE = 10

    def __init__(self, transcription_options: TranscriptionOptions,
                 input_device_index: Optional[int], sample_rate: int, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.transcription_options = transcription_options
        self.current_stream = None
        self.input_device_index = input_device_index
        self.sample_rate = sample_rate
        self.n_batch_samples = 5 * self.sample_rate  # every 5 seconds
        # pause queueing if more than 3 batches behind
        self.max_queue_size = 3 * self.n_batch_samples
        self.queue = np.ndarray([], dtype=np.float32)
        self.mutex = threading.Lock()

    @pyqtSlot(str)
    def start(self, model_path: str):
        if self.transcription_options.model.model_type == ModelType.WHISPER:
            model = whisper.load_model(model_path)
        elif self.transcription_options.model.model_type == ModelType.WHISPER_CPP:
            model = WhisperCpp(model_path)
        else:  # ModelType.HUGGING_FACE
            model = transformers_whisper.load_model(model_path)

        initial_prompt = self.transcription_options.initial_prompt

        logging.debug('Recording, transcription options = %s, model path = %s, sample rate = %s, device = %s',
                      self.transcription_options, model_path, self.sample_rate, self.input_device_index)

        self.is_running = True
        try:
            with sounddevice.InputStream(samplerate=self.sample_rate,
                                         device=self.input_device_index, dtype="float32",
                                         channels=1, callback=self.stream_callback):
                while self.is_running:
                    self.mutex.acquire()
                    if self.queue.size >= self.n_batch_samples:
                        samples = self.queue[:self.n_batch_samples]
                        self.queue = self.queue[self.n_batch_samples:]
                        self.mutex.release()

                        logging.debug('Processing next frame, sample size = %s, queue size = %s, amplitude = %s',
                                      samples.size, self.queue.size, self.amplitude(samples))
                        time_started = datetime.datetime.now()

                        if self.transcription_options.model.model_type == ModelType.WHISPER:
                            assert isinstance(model, whisper.Whisper)
                            result = model.transcribe(
                                audio=samples, language=self.transcription_options.language,
                                task=self.transcription_options.task.value,
                                initial_prompt=initial_prompt,
                                temperature=self.transcription_options.temperature)
                        elif self.transcription_options.model.model_type == ModelType.WHISPER_CPP:
                            assert isinstance(model, WhisperCpp)
                            result = model.transcribe(
                                audio=samples,
                                params=whisper_cpp_params(
                                    language=self.transcription_options.language
                                    if self.transcription_options.language is not None else 'en',
                                    task=self.transcription_options.task.value, word_level_timings=False))
                        else:
                            assert isinstance(model, TransformersWhisper)
                            result = model.transcribe(audio=samples,
                                                      language=self.transcription_options.language
                                                      if self.transcription_options.language is not None else 'en',
                                                      task=self.transcription_options.task.value)

                        next_text: str = result.get('text')

                        # Update initial prompt between successive recording chunks
                        initial_prompt += next_text

                        logging.debug('Received next result, length = %s, time taken = %s',
                                      len(next_text), datetime.datetime.now() - time_started)
                        self.transcription.emit(next_text)
                    else:
                        self.mutex.release()
        except PortAudioError as exc:
            self.error.emit(str(exc))
            logging.exception('')
            return

        self.finished.emit()

    @staticmethod
    def get_device_sample_rate(device_id: Optional[int]) -> int:
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

    def stream_callback(self, in_data: np.ndarray, frame_count, time_info, status):
        # Try to enqueue the next block. If the queue is already full, drop the block.
        chunk: np.ndarray = in_data.ravel()
        with self.mutex:
            if self.queue.size < self.max_queue_size:
                self.queue = np.append(self.queue, chunk)

    @staticmethod
    def amplitude(arr: np.ndarray):
        return (abs(max(arr)) + abs(min(arr))) / 2

    def stop_recording(self):
        self.is_running = False


class OutputFormat(enum.Enum):
    TXT = 'txt'
    SRT = 'srt'
    VTT = 'vtt'


class WhisperCppFileTranscriber(QObject):
    progress = pyqtSignal(tuple)  # (current, total)
    completed = pyqtSignal(list)  # List[Segment]
    error = pyqtSignal(str)
    duration_audio_ms = sys.maxsize  # max int
    segments: List[Segment]
    running = False

    def __init__(self, task: FileTranscriptionTask,
                 parent: Optional['QObject'] = None) -> None:
        super().__init__(parent)

        self.file_path = task.file_path
        self.language = task.transcription_options.language
        self.model_path = task.model_path
        self.task = task.transcription_options.task
        self.word_level_timings = task.transcription_options.word_level_timings
        self.segments = []

        self.process = QProcess(self)
        self.process.readyReadStandardError.connect(self.read_std_err)
        self.process.readyReadStandardOutput.connect(self.read_std_out)

    @pyqtSlot()
    def run(self):
        self.running = True
        model_path = self.model_path

        logging.debug(
            'Starting whisper_cpp file transcription, file path = %s, language = %s, task = %s, model_path = %s, '
            'word level timings = %s',
            self.file_path, self.language, self.task, model_path, self.word_level_timings)

        wav_file = tempfile.mktemp() + '.wav'
        (
            ffmpeg.input(self.file_path)
            .output(wav_file, acodec="pcm_s16le", ac=1, ar=whisper.audio.SAMPLE_RATE)
            .run(cmd=["ffmpeg", "-nostdin"], capture_stdout=True, capture_stderr=True)
        )

        args = [
            '--language', self.language if self.language is not None else 'en',
            '--max-len', '1' if self.word_level_timings else '0',
            '--model', model_path,
        ]
        if self.task == Task.TRANSLATE:
            args.append('--translate')
        args.append(wav_file)

        logging.debug(
            'Running whisper_cpp process, args = "%s"', ' '.join(args))

        self.process.start('./whisper_cpp', args)
        self.process.waitForFinished()

        # Ensure all std_out data has been read
        self.read_std_out()

        status = self.process.exitStatus()
        logging.debug('whisper_cpp process completed with status = %s', status)
        if status == QProcess.ExitStatus.NormalExit:
            self.progress.emit(
                (self.duration_audio_ms, self.duration_audio_ms))

        self.completed.emit(self.segments)
        self.running = False

    def stop(self):
        if self.running:
            process_state = self.process.state()
            if process_state == QProcess.ProcessState.Starting or process_state == QProcess.ProcessState.Running:
                self.process.terminate()

    def read_std_out(self):
        try:
            output = self.process.readAllStandardOutput().data().decode('UTF-8').strip()
            if len(output) > 0:
                lines = output.split('\n')
                for line in lines:
                    timings, text = line.split('  ')
                    start, end = self.parse_timings(timings)
                    segment = Segment(start, end, text.strip())
                    self.segments.append(segment)
                    self.progress.emit((end, self.duration_audio_ms))
        except (UnicodeDecodeError, ValueError):
            pass

    def parse_timings(self, timings: str) -> Tuple[int, int]:
        start, end = timings[1:len(timings) - 1].split(' --> ')
        return self.parse_timestamp(start), self.parse_timestamp(end)

    @staticmethod
    def parse_timestamp(timestamp: str) -> int:
        hrs, mins, secs_ms = timestamp.split(':')
        secs, ms = secs_ms.split('.')
        return int(hrs) * 60 * 60 * 1000 + int(mins) * 60 * 1000 + int(secs) * 1000 + int(ms)

    def read_std_err(self):
        try:
            output = self.process.readAllStandardError().data().decode('UTF-8').strip()
            logging.debug('whisper_cpp (stderr): %s', output)

            lines = output.split('\n')
            for line in lines:
                if line.startswith('main: processing'):
                    match = re.search(r'samples, (.*) sec', line)
                    if match is not None:
                        self.duration_audio_ms = round(
                            float(match.group(1)) * 1000)
        except UnicodeDecodeError:
            pass


class WhisperFileTranscriber(QObject):
    """WhisperFileTranscriber transcribes an audio file to text, writes the text to a file, and then opens the file
    using the default program for opening txt files. """

    current_process: multiprocessing.Process
    progress = pyqtSignal(tuple)  # (current, total)
    completed = pyqtSignal(list)  # List[Segment]
    error = pyqtSignal(str)
    running = False
    read_line_thread: Optional[Thread] = None
    READ_LINE_THREAD_STOP_TOKEN = '--STOP--'

    def __init__(self, task: FileTranscriptionTask,
                 parent: Optional['QObject'] = None) -> None:
        super().__init__(parent)
        self.transcription_task = task
        self.segments = []
        self.started_process = False
        self.stopped = False

    @pyqtSlot()
    def run(self):
        time_started = datetime.datetime.now()
        logging.debug(
            'Starting whisper file transcription, task = %s', self.transcription_task)

        recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)

        self.current_process = multiprocessing.Process(target=transcribe_whisper,
                                                       args=(send_pipe, self.transcription_task))
        if not self.stopped:
            self.current_process.start()
            self.started_process = True

        self.read_line_thread = Thread(
            target=self.read_line, args=(recv_pipe,))
        self.read_line_thread.start()

        self.current_process.join()

        if self.current_process.exitcode != 0:
            send_pipe.close()

        self.read_line_thread.join()

        logging.debug(
            'whisper process completed with code = %s, time taken = %s, number of segments = %s',
            self.current_process.exitcode, datetime.datetime.now() - time_started, len(self.segments))

        if self.current_process.exitcode == 0:
            self.completed.emit(self.segments)
        else:
            self.error.emit('Unknown error')

    def stop(self):
        self.stopped = True
        if self.started_process:
            self.current_process.terminate()

    def read_line(self, pipe: Connection):
        while True:
            try:
                line = pipe.recv().strip()
            except EOFError:  # Connection closed
                break

            if line == self.READ_LINE_THREAD_STOP_TOKEN:
                return

            if line.startswith('segments = '):
                segments_dict = json.loads(line[11:])
                segments = [Segment(
                    start=segment.get('start'),
                    end=segment.get('end'),
                    text=segment.get('text'),
                ) for segment in segments_dict]
                self.segments = segments
            else:
                try:
                    progress = int(line.split('|')[0].strip().strip('%'))
                    self.progress.emit((progress, 100))
                except ValueError:
                    logging.debug('whisper (stderr): %s', line)
                    continue


def transcribe_whisper(stderr_conn: Connection, task: FileTranscriptionTask):
    with pipe_stderr(stderr_conn):
        if task.transcription_options.model.model_type == ModelType.HUGGING_FACE:
            model = transformers_whisper.load_model(task.model_path)
            language = task.transcription_options.language if task.transcription_options.language is not None else 'en'
            result = model.transcribe(audio=task.file_path, language=language,
                                      task=task.transcription_options.task.value, verbose=False)
            whisper_segments = result.get('segments')
        else:
            model = whisper.load_model(task.model_path)
            if task.transcription_options.word_level_timings:
                stable_whisper.modify_model(model)
                result = model.transcribe(
                    audio=task.file_path, language=task.transcription_options.language,
                    task=task.transcription_options.task.value, temperature=task.transcription_options.temperature,
                    initial_prompt=task.transcription_options.initial_prompt, pbar=True)
                whisper_segments = stable_whisper.group_word_timestamps(result)
            else:
                result = model.transcribe(
                    audio=task.file_path, language=task.transcription_options.language,
                    task=task.transcription_options.task.value,
                    temperature=task.transcription_options.temperature,
                    initial_prompt=task.transcription_options.initial_prompt, verbose=False)
                whisper_segments = result.get('segments')

        segments = [
            Segment(
                start=int(segment.get('start') * 1000),
                end=int(segment.get('end') * 1000),
                text=segment.get('text'),
            ) for segment in whisper_segments]
        segments_json = json.dumps(
            segments, ensure_ascii=True, default=vars)
        sys.stderr.write(f'segments = {segments_json}\n')
        sys.stderr.write(
            WhisperFileTranscriber.READ_LINE_THREAD_STOP_TOKEN + '\n')


def write_output(path: str, segments: List[Segment], should_open: bool, output_format: OutputFormat):
    logging.debug(
        'Writing transcription output, path = %s, output format = %s, number of segments = %s', path, output_format,
        len(segments))

    with open(path, 'w', encoding='utf-8') as file:
        if output_format == OutputFormat.TXT:
            for (i, segment) in enumerate(segments):
                file.write(segment.text)
                if i < len(segments) - 1:
                    file.write(' ')
            file.write('\n')

        elif output_format == OutputFormat.VTT:
            file.write('WEBVTT\n\n')
            for segment in segments:
                file.write(
                    f'{to_timestamp(segment.start)} --> {to_timestamp(segment.end)}\n')
                file.write(f'{segment.text}\n\n')

        elif output_format == OutputFormat.SRT:
            for (i, segment) in enumerate(segments):
                file.write(f'{i + 1}\n')
                file.write(
                    f'{to_timestamp(segment.start, ms_separator=",")} --> {to_timestamp(segment.end, ms_separator=",")}\n')
                file.write(f'{segment.text}\n\n')

    logging.debug('Written transcription output')

    if should_open:
        try:
            logging.debug('Opening transcription output')
            os.startfile(path)
        except AttributeError:
            opener = "open" if platform.system() == "Darwin" else "xdg-open"
            subprocess.call([opener, path])


def segments_to_text(segments: List[Segment]) -> str:
    result = ''
    for (i, segment) in enumerate(segments):
        result += f'{to_timestamp(segment.start)} --> {to_timestamp(segment.end)}\n'
        result += f'{segment.text}'
        if i < len(segments) - 1:
            result += '\n\n'
    return result


def to_timestamp(ms: float, ms_separator='.') -> str:
    hr = int(ms / (1000 * 60 * 60))
    ms = ms - hr * (1000 * 60 * 60)
    min = int(ms / (1000 * 60))
    ms = ms - min * (1000 * 60)
    sec = int(ms / 1000)
    ms = int(ms - sec * 1000)
    return f'{hr:02d}:{min:02d}:{sec:02d}{ms_separator}{ms:03d}'


SUPPORTED_OUTPUT_FORMATS = 'Audio files (*.mp3 *.wav *.m4a *.ogg);;\
Video files (*.mp4 *.webm *.ogm *.mov);;All files (*.*)'


def get_default_output_file_path(task: Task, input_file_path: str, output_format: OutputFormat):
    return f'{os.path.splitext(input_file_path)[0]} ({task.value.title()}d on {datetime.datetime.now():%d-%b-%Y %H-%M-%S}).{output_format.value}'


def whisper_cpp_params(
        language: str, task: Task, word_level_timings: bool,
        print_realtime=False, print_progress=False, ):
    params = whisper_cpp.whisper_full_default_params(
        whisper_cpp.WHISPER_SAMPLING_GREEDY)
    params.print_realtime = print_realtime
    params.print_progress = print_progress
    params.language = whisper_cpp.String(language.encode('utf-8'))
    params.translate = task == Task.TRANSLATE
    params.max_len = ctypes.c_int(1)
    params.max_len = 1 if word_level_timings else 0
    params.token_timestamps = word_level_timings
    return params


class WhisperCpp:
    def __init__(self, model: str) -> None:
        self.ctx = whisper_cpp.whisper_init_from_file(model.encode('utf-8'))

    def transcribe(self, audio: Union[np.ndarray, str], params: Any):
        if isinstance(audio, str):
            audio = whisper.audio.load_audio(audio)

        logging.debug('Loaded audio with length = %s', len(audio))

        whisper_cpp_audio = audio.ctypes.data_as(
            ctypes.POINTER(ctypes.c_float))
        result = whisper_cpp.whisper_full(
            self.ctx, params, whisper_cpp_audio, len(audio))
        if result != 0:
            raise Exception(f'Error from whisper.cpp: {result}')

        segments: List[Segment] = []

        n_segments = whisper_cpp.whisper_full_n_segments((self.ctx))
        for i in range(n_segments):
            txt = whisper_cpp.whisper_full_get_segment_text((self.ctx), i)
            t0 = whisper_cpp.whisper_full_get_segment_t0((self.ctx), i)
            t1 = whisper_cpp.whisper_full_get_segment_t1((self.ctx), i)

            segments.append(
                Segment(start=t0 * 10,  # centisecond to ms
                        end=t1 * 10,  # centisecond to ms
                        text=txt.decode('utf-8')))

        return {
            'segments': segments,
            'text': ''.join([segment.text for segment in segments])}

    def __del__(self):
        whisper_cpp.whisper_free(self.ctx)


class FileTranscriberQueueWorker(QObject):
    tasks_queue: multiprocessing.Queue
    current_task: Optional[FileTranscriptionTask] = None
    current_transcriber: Optional[WhisperFileTranscriber |
                                  WhisperCppFileTranscriber] = None
    current_transcriber_thread: Optional[QThread] = None
    task_updated = pyqtSignal(FileTranscriptionTask)
    completed = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.tasks_queue = queue.Queue()
        self.canceled_tasks = set()

    @pyqtSlot()
    def run(self):
        logging.debug('Waiting for next transcription task')

        # Waiting for new tasks in a loop instead of with queue.wait()
        # resolves a "No Python frame" crash when the thread is quit.
        while True:
            try:
                self.current_task: Optional[FileTranscriptionTask] = self.tasks_queue.get_nowait()

                # Stop listening when a "None" task is received
                if self.current_task is None:
                    self.completed.emit()
                    return

                if self.current_task.id in self.canceled_tasks:
                    continue

                break
            except queue.Empty:
                continue

        logging.debug('Starting next transcription task')

        if self.current_task.transcription_options.model.model_type == ModelType.WHISPER_CPP:
            self.current_transcriber = WhisperCppFileTranscriber(
                task=self.current_task)
        else:
            self.current_transcriber = WhisperFileTranscriber(
                task=self.current_task)

        self.current_transcriber_thread = QThread(self)

        self.current_transcriber.moveToThread(self.current_transcriber_thread)

        self.current_transcriber_thread.started.connect(
            self.current_transcriber.run)
        self.current_transcriber.completed.connect(
            self.current_transcriber_thread.quit)
        self.current_transcriber.error.connect(
            self.current_transcriber_thread.quit)

        self.current_transcriber.completed.connect(
            self.current_transcriber.deleteLater)
        self.current_transcriber.error.connect(
            self.current_transcriber.deleteLater)
        self.current_transcriber_thread.finished.connect(
            self.current_transcriber_thread.deleteLater)

        self.current_transcriber.progress.connect(self.on_task_progress)
        self.current_transcriber.error.connect(self.on_task_error)

        self.current_transcriber.completed.connect(self.on_task_completed)

        # Wait for next item on the queue
        self.current_transcriber.error.connect(self.run)
        self.current_transcriber.completed.connect(self.run)

        self.current_transcriber_thread.start()

    def add_task(self, task: FileTranscriptionTask):
        self.tasks_queue.put(task)
        task.status = FileTranscriptionTask.Status.QUEUED
        self.task_updated.emit(task)

    def cancel_task(self, task_id: int):
        self.canceled_tasks.add(task_id)

        if self.current_task.id == task_id:
            if self.current_transcriber is not None:
                self.current_transcriber.stop()

    @pyqtSlot(str)
    def on_task_error(self, error: str):
        if self.current_task is not None and self.current_task.id not in self.canceled_tasks:
            self.current_task.status = FileTranscriptionTask.Status.FAILED
            self.current_task.error = error
            self.task_updated.emit(self.current_task)

    @pyqtSlot(tuple)
    def on_task_progress(self, progress: Tuple[int, int]):
        if self.current_task is not None:
            self.current_task.status = FileTranscriptionTask.Status.IN_PROGRESS
            self.current_task.fraction_completed = progress[0] / progress[1]
            self.task_updated.emit(self.current_task)

    @pyqtSlot(list)
    def on_task_completed(self, segments: List[Segment]):
        if self.current_task is not None:
            self.current_task.status = FileTranscriptionTask.Status.COMPLETED
            self.current_task.segments = segments
            self.task_updated.emit(self.current_task)

    def stop(self):
        self.tasks_queue.put(None)
        if self.current_transcriber is not None:
            self.current_transcriber.stop()
