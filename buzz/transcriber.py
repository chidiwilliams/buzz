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
from dataclasses import dataclass
from multiprocessing.connection import Connection
from threading import Thread
from typing import Any, Callable, List, Optional, Tuple, Union

import ffmpeg
import numpy as np
import sounddevice
import stable_whisper
import whisper
from PyQt6.QtCore import QObject, QProcess, pyqtSignal, pyqtSlot
from sounddevice import PortAudioError

from .conn import pipe_stderr

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
                 temperature: Tuple[float, ...] = DEFAULT_WHISPER_TEMPERATURE, initial_prompt: str = '',
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
        self.temperature = temperature
        self.initial_prompt = initial_prompt
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
            'Recording, language = %s, task = %s, device = %s, sample rate = %s, model_path = %s, temperature = %s, initial prompt length = %s',
            self.language, self.task, self.input_device_index, self.sample_rate, self.model_path, self.temperature, len(self.initial_prompt))
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
                        audio=samples, language=self.language,
                        task=self.task.value, initial_prompt=self.initial_prompt,
                        temperature=self.temperature)
                else:
                    result = model.transcribe(
                        audio=samples,
                        params=whisper_cpp_params(
                            language=self.language if self.language is not None else 'en',
                            task=self.task.value, word_level_timings=False))

                next_text: str = result.get('text')

                # Update initial prompt between successive recording chunks
                self.initial_prompt += next_text

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


@dataclass
class FileTranscriptionOptions:
    file_path: str
    language: Optional[str] = None
    task: Task = Task.TRANSCRIBE
    word_level_timings: bool = False
    temperature: Tuple[float, ...] = DEFAULT_WHISPER_TEMPERATURE
    initial_prompt: str = ''


class WhisperCppFileTranscriber(QObject):
    progress = pyqtSignal(tuple)  # (current, total)
    completed = pyqtSignal(tuple)  # (exit_code: int, segments: List[Segment])
    error = pyqtSignal(str)
    duration_audio_ms = sys.maxsize  # max int
    segments: List[Segment]
    running = False

    def __init__(
            self, transcription_options: FileTranscriptionOptions,
            parent: Optional['QObject'] = None) -> None:
        super().__init__(parent)

        self.file_path = transcription_options.file_path
        self.language = transcription_options.language
        self.task = transcription_options.task
        self.word_level_timings = transcription_options.word_level_timings
        self.segments = []

        self.process = QProcess(self)
        self.process.readyReadStandardError.connect(self.read_std_err)
        self.process.readyReadStandardOutput.connect(self.read_std_out)

    @pyqtSlot(str)
    def run(self, model_path: str):
        self.running = True

        logging.debug(
            'Starting whisper_cpp file transcription, file path = %s, language = %s, task = %s, model_path = %s',
            self.file_path, self.language, self.task, model_path)

        wav_file = tempfile.mktemp()+'.wav'
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

        status = self.process.exitStatus()
        logging.debug('whisper_cpp process completed with status = %s', status)
        if status == QProcess.ExitStatus.NormalExit:
            self.progress.emit(
                (self.duration_audio_ms, self.duration_audio_ms))

        self.completed.emit((self.process.exitCode(), self.segments))
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
        start, end = timings[1:len(timings)-1].split(' --> ')
        return self.parse_timestamp(start), self.parse_timestamp(end)

    def parse_timestamp(self, timestamp: str) -> int:
        hrs, mins, secs_ms = timestamp.split(':')
        secs, ms = secs_ms.split('.')
        return int(hrs)*60*60*1000 + int(mins)*60*1000 + int(secs)*1000 + int(ms)

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
                            float(match.group(1))*1000)
        except UnicodeDecodeError:
            pass


class WhisperFileTranscriber(QObject):
    """WhisperFileTranscriber transcribes an audio file to text, writes the text to a file, and then opens the file using the default program for opening txt files."""

    current_process: multiprocessing.Process
    progress = pyqtSignal(tuple)  # (current, total)
    completed = pyqtSignal(tuple)  # (exit_code: int, segments: List[Segment])
    error = pyqtSignal(str)
    running = False
    read_line_thread: Optional[Thread] = None
    segments: List[Segment]

    def __init__(
            self, transcription_options: FileTranscriptionOptions,
            parent: Optional['QObject'] = None) -> None:
        super().__init__(parent)

        self.file_path = transcription_options.file_path
        self.language = transcription_options.language
        self.task = transcription_options.task
        self.word_level_timings = transcription_options.word_level_timings
        self.temperature = transcription_options.temperature
        self.initial_prompt = transcription_options.initial_prompt
        self.segments = []

    @pyqtSlot(str)
    def run(self, model_path: str):
        self.running = True
        time_started = datetime.datetime.now()
        logging.debug(
            'Starting whisper file transcription, file path = %s, language = %s, task = %s, model path = %s, temperature = %s, initial prompt length = %s',
            self.file_path, self.language, self.task, model_path, self.temperature, len(self.initial_prompt))

        recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)

        self.current_process = multiprocessing.Process(
            target=transcribe_whisper,
            args=(
                send_pipe, model_path, self.file_path,
                self.language, self.task, self.word_level_timings,
                self.temperature, self.initial_prompt
            ))

        self.current_process.start()

        self.read_line_thread = Thread(target=self.read_line, args=(
            recv_pipe, self.on_whisper_stdout))
        self.read_line_thread.start()

        self.current_process.join()

        logging.debug(
            'whisper process completed with code = %s, time taken = %s',
            self.current_process.exitcode, datetime.datetime.now()-time_started)

        recv_pipe.close()
        send_pipe.close()

        self.read_line_thread.join()

        if self.current_process.exitcode != 0:
            self.completed.emit((self.current_process.exitcode, []))

        self.running = False

    def stop(self):
        if self.running:
            self.current_process.terminate()

    def on_whisper_stdout(self, line: str):
        if line.startswith('segments = '):
            segments_dict = json.loads(line[11:])
            self.segments = [Segment(
                start=segment.get('start'),
                end=segment.get('end'),
                text=segment.get('text'),
            ) for segment in segments_dict]
            self.completed.emit((self.current_process.exitcode, self.segments))
            return

        try:
            progress = int(line.split('|')[0].strip().strip('%'))
            self.progress.emit((progress, 100))
        except ValueError:
            pass

    def read_line(self, pipe: Connection, callback: Callable[[str], None]):
        while pipe.closed is False:
            try:
                text = pipe.recv().strip()
                callback(text)
            except EOFError:
                break


def transcribe_whisper(
        stderr_conn: Connection, model_path: str, file_path: str,
        language: Optional[str], task: Task,
        word_level_timings: bool, temperature: Tuple[float, ...], initial_prompt: str):
    with pipe_stderr(stderr_conn):
        model = whisper.load_model(model_path)

        if word_level_timings:
            stable_whisper.modify_model(model)
            result = model.transcribe(
                audio=file_path, language=language,
                task=task.value, temperature=temperature,
                initial_prompt=initial_prompt, pbar=True)
        else:
            result = model.transcribe(
                audio=file_path, language=language, task=task.value, temperature=temperature,
                initial_prompt=initial_prompt, verbose=False)

        whisper_segments = stable_whisper.group_word_timestamps(
            result) if word_level_timings else result.get('segments')

        segments = [
            Segment(
                start=int(segment.get('start')*1000),
                end=int(segment.get('end')*1000),
                text=segment.get('text'),
            ) for segment in whisper_segments]
        segments_json = json.dumps(
            segments, ensure_ascii=True, default=vars)
        sys.stderr.write(f'segments = {segments_json}\n')


def write_output(path: str, segments: List[Segment], should_open: bool, output_format: OutputFormat):
    logging.debug(
        'Writing transcription output, path = %s, output format = %s, number of segments = %s', path, output_format, len(segments))

    with open(path, 'w', encoding='utf-8') as file:
        if output_format == OutputFormat.TXT:
            for (i, segment) in enumerate(segments):
                file.write(segment.text)
                if i < len(segments)-1:
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


def segments_to_text(segments: List[Segment]) -> str:
    result = ''
    for (i, segment) in enumerate(segments):
        result += f'{to_timestamp(segment.start)} --> {to_timestamp(segment.end)}\n'
        result += f'{segment.text}'
        if i < len(segments)-1:
            result += '\n\n'
    return result


def to_timestamp(ms: float) -> str:
    hr = int(ms / (1000*60*60))
    ms = ms - hr * (1000*60*60)
    min = int(ms / (1000*60))
    ms = ms - min * (1000*60)
    sec = int(ms / 1000)
    ms = int(ms - sec * 1000)
    return f'{hr:02d}:{min:02d}:{sec:02d}.{ms:03d}'


SUPPORTED_OUTPUT_FORMATS = 'Audio files (*.mp3 *.wav *.m4a *.ogg);;\
Video files (*.mp4 *.webm *.ogm *.mov);;All files (*.*)'


def get_default_output_file_path(task: Task, input_file_path: str, output_format: OutputFormat):
    return f'{os.path.splitext(input_file_path)[0]} ({task.value.title()}d on {datetime.datetime.now():%d-%b-%Y %H-%M-%S}).{output_format.value}'


def whisper_cpp_params(
        language: str, task: Task, word_level_timings: bool,
        print_realtime=False, print_progress=False,):
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
        self.ctx = whisper_cpp.whisper_init(model.encode('utf-8'))

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
                Segment(start=t0*10,  # centisecond to ms
                        end=t1*10,  # centisecond to ms
                        text=txt.decode('utf-8')))

        return {
            'segments': segments,
            'text': ''.join([segment.text for segment in segments])}

    def __del__(self):
        whisper_cpp.whisper_free((self.ctx))
