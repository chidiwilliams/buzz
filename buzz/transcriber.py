import ctypes
import datetime
import enum
import json
import logging
import multiprocessing
import os
import subprocess
import sys
import tempfile
from abc import abstractmethod
from dataclasses import dataclass, field
from multiprocessing.connection import Connection
from random import randint
from threading import Thread
from typing import Any, List, Optional, Tuple, Union, Set

import faster_whisper
import numpy as np
import openai
import stable_whisper
import tqdm
import whisper
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from dataclasses_json import dataclass_json, config, Exclude
from whisper import tokenizer

from . import transformers_whisper
from .conn import pipe_stderr
from .model_loader import TranscriptionModel, ModelType

# Catch exception from whisper.dll not getting loaded.
# TODO: Remove flag and try-except when issue with loading
# the DLL in some envs is fixed.
LOADED_WHISPER_DLL = False
try:
    import buzz.whisper_cpp as whisper_cpp

    LOADED_WHISPER_DLL = True
except ImportError:
    logging.exception("")

DEFAULT_WHISPER_TEMPERATURE = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


class Task(enum.Enum):
    TRANSLATE = "translate"
    TRANSCRIBE = "transcribe"


@dataclass
class Segment:
    start: int  # start time in ms
    end: int  # end time in ms
    text: str


LANGUAGES = tokenizer.LANGUAGES


@dataclass()
class TranscriptionOptions:
    language: Optional[str] = None
    task: Task = Task.TRANSCRIBE
    model: TranscriptionModel = field(default_factory=TranscriptionModel)
    word_level_timings: bool = False
    temperature: Tuple[float, ...] = DEFAULT_WHISPER_TEMPERATURE
    initial_prompt: str = ""
    openai_access_token: str = field(
        default="", metadata=config(exclude=Exclude.ALWAYS)
    )


@dataclass()
class FileTranscriptionOptions:
    file_paths: List[str]
    output_formats: Set["OutputFormat"] = field(default_factory=set)
    default_output_file_name: str = ""


@dataclass_json
@dataclass
class FileTranscriptionTask:
    class Status(enum.Enum):
        QUEUED = "queued"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELED = "canceled"

    file_path: str
    transcription_options: TranscriptionOptions
    file_transcription_options: FileTranscriptionOptions
    model_path: str
    id: int = field(default_factory=lambda: randint(0, 100_000_000))
    segments: List[Segment] = field(default_factory=list)
    status: Optional[Status] = None
    fraction_completed = 0.0
    error: Optional[str] = None
    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None


class OutputFormat(enum.Enum):
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"


class FileTranscriber(QObject):
    transcription_task: FileTranscriptionTask
    progress = pyqtSignal(tuple)  # (current, total)
    completed = pyqtSignal(list)  # List[Segment]
    error = pyqtSignal(Exception)

    def __init__(self, task: FileTranscriptionTask, parent: Optional["QObject"] = None):
        super().__init__(parent)
        self.transcription_task = task

    @pyqtSlot()
    def run(self):
        try:
            segments = self.transcribe()
        except Exception as exc:
            self.error.emit(exc)
            return

        self.completed.emit(segments)

        for (
            output_format
        ) in self.transcription_task.file_transcription_options.output_formats:
            default_path = get_default_output_file_path(
                task=self.transcription_task, output_format=output_format
            )

            write_output(
                path=default_path, segments=segments, output_format=output_format
            )

    @abstractmethod
    def transcribe(self) -> List[Segment]:
        ...

    @abstractmethod
    def stop(self):
        ...


class Stopped(Exception):
    pass


class WhisperCppFileTranscriber(FileTranscriber):
    duration_audio_ms = sys.maxsize  # max int
    state: "WhisperCppFileTranscriber.State"

    class State:
        running = True

    def __init__(
        self, task: FileTranscriptionTask, parent: Optional["QObject"] = None
    ) -> None:
        super().__init__(task, parent)

        self.file_path = task.file_path
        self.language = task.transcription_options.language
        self.model_path = task.model_path
        self.task = task.transcription_options.task
        self.word_level_timings = task.transcription_options.word_level_timings
        self.state = self.State()

    def transcribe(self) -> List[Segment]:
        self.state.running = True
        model_path = self.model_path

        logging.debug(
            "Starting whisper_cpp file transcription, file path = %s, language = %s, task = %s, model_path = %s, "
            "word level timings = %s",
            self.file_path,
            self.language,
            self.task,
            model_path,
            self.word_level_timings,
        )

        audio = whisper.audio.load_audio(self.file_path)
        self.duration_audio_ms = len(audio) * 1000 / whisper.audio.SAMPLE_RATE

        whisper_params = whisper_cpp_params(
            language=self.language if self.language is not None else "",
            task=self.task,
            word_level_timings=self.word_level_timings,
        )
        whisper_params.encoder_begin_callback_user_data = ctypes.c_void_p(
            id(self.state)
        )
        whisper_params.encoder_begin_callback = (
            whisper_cpp.whisper_encoder_begin_callback(self.encoder_begin_callback)
        )
        whisper_params.new_segment_callback_user_data = ctypes.c_void_p(id(self.state))
        whisper_params.new_segment_callback = whisper_cpp.whisper_new_segment_callback(
            self.new_segment_callback
        )

        model = WhisperCpp(model=model_path)
        result = model.transcribe(audio=self.file_path, params=whisper_params)

        if not self.state.running:
            raise Stopped

        self.state.running = False
        return result["segments"]

    def new_segment_callback(self, ctx, _state, _n_new, user_data):
        n_segments = whisper_cpp.whisper_full_n_segments(ctx)
        t1 = whisper_cpp.whisper_full_get_segment_t1(ctx, n_segments - 1)
        # t1 seems to sometimes be larger than the duration when the
        # audio ends in silence. Trim to fix the displayed progress.
        progress = min(t1 * 10, self.duration_audio_ms)
        state: WhisperCppFileTranscriber.State = ctypes.cast(
            user_data, ctypes.py_object
        ).value
        if state.running:
            self.progress.emit((progress, self.duration_audio_ms))

    @staticmethod
    def encoder_begin_callback(_ctx, _state, user_data):
        state: WhisperCppFileTranscriber.State = ctypes.cast(
            user_data, ctypes.py_object
        ).value
        return state.running == 1

    def stop(self):
        self.state.running = False


class OpenAIWhisperAPIFileTranscriber(FileTranscriber):
    def __init__(self, task: FileTranscriptionTask, parent: Optional["QObject"] = None):
        super().__init__(task=task, parent=parent)
        self.file_path = task.file_path
        self.task = task.transcription_options.task

    def transcribe(self) -> List[Segment]:
        logging.debug(
            "Starting OpenAI Whisper API file transcription, file path = %s, task = %s",
            self.file_path,
            self.task,
        )

        wav_file = tempfile.mktemp() + ".wav"

        # fmt: off
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-threads", "0",
            "-i", self.file_path,
            "-f", "s16le",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-ar", str(whisper.audio.SAMPLE_RATE),
            wav_file,
        ]
        # fmt: on

        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError as exc:
            logging.exception("")
            raise Exception(exc.stderr.decode("utf-8"))

        # TODO: Check if file size is more than 25MB (2.5 minutes), then chunk
        audio_file = open(wav_file, "rb")
        openai.api_key = (
            self.transcription_task.transcription_options.openai_access_token
        )
        language = self.transcription_task.transcription_options.language
        response_format = "verbose_json"
        if self.transcription_task.transcription_options.task == Task.TRANSLATE:
            transcript = openai.Audio.translate(
                "whisper-1",
                audio_file,
                response_format=response_format,
                language=language,
            )
        else:
            transcript = openai.Audio.transcribe(
                "whisper-1",
                audio_file,
                response_format=response_format,
                language=language,
            )

        segments = [
            Segment(segment["start"] * 1000, segment["end"] * 1000, segment["text"])
            for segment in transcript["segments"]
        ]
        return segments

    def stop(self):
        pass


class WhisperFileTranscriber(FileTranscriber):
    """WhisperFileTranscriber transcribes an audio file to text, writes the text to a file, and then opens the file
    using the default program for opening txt files."""

    current_process: multiprocessing.Process
    running = False
    read_line_thread: Optional[Thread] = None
    READ_LINE_THREAD_STOP_TOKEN = "--STOP--"

    def __init__(
        self, task: FileTranscriptionTask, parent: Optional["QObject"] = None
    ) -> None:
        super().__init__(task, parent)
        self.segments = []
        self.started_process = False
        self.stopped = False

    def transcribe(self) -> List[Segment]:
        time_started = datetime.datetime.now()
        logging.debug(
            "Starting whisper file transcription, task = %s", self.transcription_task
        )

        recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)

        self.current_process = multiprocessing.Process(
            target=self.transcribe_whisper, args=(send_pipe, self.transcription_task)
        )
        if not self.stopped:
            self.current_process.start()
            self.started_process = True

        self.read_line_thread = Thread(target=self.read_line, args=(recv_pipe,))
        self.read_line_thread.start()

        self.current_process.join()

        if self.current_process.exitcode != 0:
            send_pipe.close()

        self.read_line_thread.join()

        logging.debug(
            "whisper process completed with code = %s, time taken = %s, number of segments = %s",
            self.current_process.exitcode,
            datetime.datetime.now() - time_started,
            len(self.segments),
        )

        if self.current_process.exitcode != 0:
            raise Exception("Unknown error")

        return self.segments

    @classmethod
    def transcribe_whisper(
        cls, stderr_conn: Connection, task: FileTranscriptionTask
    ) -> None:
        with pipe_stderr(stderr_conn):
            if task.transcription_options.model.model_type == ModelType.HUGGING_FACE:
                segments = cls.transcribe_hugging_face(task)
            elif (
                task.transcription_options.model.model_type == ModelType.FASTER_WHISPER
            ):
                segments = cls.transcribe_faster_whisper(task)
            elif task.transcription_options.model.model_type == ModelType.WHISPER:
                segments = cls.transcribe_openai_whisper(task)
            else:
                raise Exception(
                    f"Invalid model type: {task.transcription_options.model.model_type}"
                )

            segments_json = json.dumps(segments, ensure_ascii=True, default=vars)
            sys.stderr.write(f"segments = {segments_json}\n")
            sys.stderr.write(WhisperFileTranscriber.READ_LINE_THREAD_STOP_TOKEN + "\n")

    @classmethod
    def transcribe_hugging_face(cls, task: FileTranscriptionTask) -> List[Segment]:
        model = transformers_whisper.load_model(task.model_path)
        language = (
            task.transcription_options.language
            if task.transcription_options.language is not None
            else "en"
        )
        result = model.transcribe(
            audio=task.file_path,
            language=language,
            task=task.transcription_options.task.value,
            verbose=False,
        )
        return [
            Segment(
                start=int(segment.get("start") * 1000),
                end=int(segment.get("end") * 1000),
                text=segment.get("text"),
            )
            for segment in result.get("segments")
        ]

    @classmethod
    def transcribe_faster_whisper(cls, task: FileTranscriptionTask) -> List[Segment]:
        model = faster_whisper.WhisperModel(
            model_size_or_path=task.transcription_options.model.whisper_model_size.to_faster_whisper_model_size()
        )
        whisper_segments, info = model.transcribe(
            audio=task.file_path,
            language=task.transcription_options.language,
            task=task.transcription_options.task.value,
            temperature=task.transcription_options.temperature,
            initial_prompt=task.transcription_options.initial_prompt,
            word_timestamps=task.transcription_options.word_level_timings,
        )
        segments = []
        with tqdm.tqdm(total=round(info.duration, 2), unit=" seconds") as pbar:
            for segment in list(whisper_segments):
                # Segment will contain words if word-level timings is True
                if segment.words:
                    for word in segment.words:
                        segments.append(
                            Segment(
                                start=int(word.start * 1000),
                                end=int(word.end * 1000),
                                text=word.word,
                            )
                        )
                else:
                    segments.append(
                        Segment(
                            start=int(segment.start * 1000),
                            end=int(segment.end * 1000),
                            text=segment.text,
                        )
                    )

                pbar.update(segment.end - segment.start)
        return segments

    @classmethod
    def transcribe_openai_whisper(cls, task: FileTranscriptionTask) -> List[Segment]:
        model = whisper.load_model(task.model_path)

        if task.transcription_options.word_level_timings:
            stable_whisper.modify_model(model)
            result = model.transcribe(
                audio=task.file_path,
                language=task.transcription_options.language,
                task=task.transcription_options.task.value,
                temperature=task.transcription_options.temperature,
                initial_prompt=task.transcription_options.initial_prompt,
                pbar=True,
            )
            segments = stable_whisper.group_word_timestamps(result)
            return [
                Segment(
                    start=int(segment.get("start") * 1000),
                    end=int(segment.get("end") * 1000),
                    text=segment.get("text"),
                )
                for segment in segments
            ]

        result = model.transcribe(
            audio=task.file_path,
            language=task.transcription_options.language,
            task=task.transcription_options.task.value,
            temperature=task.transcription_options.temperature,
            initial_prompt=task.transcription_options.initial_prompt,
            verbose=False,
        )
        segments = result.get("segments")
        return [
            Segment(
                start=int(segment.get("start") * 1000),
                end=int(segment.get("end") * 1000),
                text=segment.get("text"),
            )
            for segment in segments
        ]

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

            if line.startswith("segments = "):
                segments_dict = json.loads(line[11:])
                segments = [
                    Segment(
                        start=segment.get("start"),
                        end=segment.get("end"),
                        text=segment.get("text"),
                    )
                    for segment in segments_dict
                ]
                self.segments = segments
            else:
                try:
                    progress = int(line.split("|")[0].strip().strip("%"))
                    self.progress.emit((progress, 100))
                except ValueError:
                    logging.debug("whisper (stderr): %s", line)
                    continue


def write_output(path: str, segments: List[Segment], output_format: OutputFormat):
    logging.debug(
        "Writing transcription output, path = %s, output format = %s, number of segments = %s",
        path,
        output_format,
        len(segments),
    )

    with open(path, "w", encoding="utf-8") as file:
        if output_format == OutputFormat.TXT:
            for i, segment in enumerate(segments):
                file.write(segment.text)
                file.write("\n")

        elif output_format == OutputFormat.VTT:
            file.write("WEBVTT\n\n")
            for segment in segments:
                file.write(
                    f"{to_timestamp(segment.start)} --> {to_timestamp(segment.end)}\n"
                )
                file.write(f"{segment.text}\n\n")

        elif output_format == OutputFormat.SRT:
            for i, segment in enumerate(segments):
                file.write(f"{i + 1}\n")
                file.write(
                    f'{to_timestamp(segment.start, ms_separator=",")} --> {to_timestamp(segment.end, ms_separator=",")}\n'
                )
                file.write(f"{segment.text}\n\n")

    logging.debug("Written transcription output")


def segments_to_text(segments: List[Segment]) -> str:
    result = ""
    for i, segment in enumerate(segments):
        result += f"{to_timestamp(segment.start)} --> {to_timestamp(segment.end)}\n"
        result += f"{segment.text}"
        if i < len(segments) - 1:
            result += "\n\n"
    return result


def to_timestamp(ms: float, ms_separator=".") -> str:
    hr = int(ms / (1000 * 60 * 60))
    ms = ms - hr * (1000 * 60 * 60)
    min = int(ms / (1000 * 60))
    ms = ms - min * (1000 * 60)
    sec = int(ms / 1000)
    ms = int(ms - sec * 1000)
    return f"{hr:02d}:{min:02d}:{sec:02d}{ms_separator}{ms:03d}"


SUPPORTED_OUTPUT_FORMATS = "Audio files (*.mp3 *.wav *.m4a *.ogg);;\
Video files (*.mp4 *.webm *.ogm *.mov);;All files (*.*)"


def get_default_output_file_path(
    task: FileTranscriptionTask, output_format: OutputFormat
):
    input_file_name = os.path.splitext(task.file_path)[0]
    date_time_now = datetime.datetime.now().strftime("%d-%b-%Y %H-%M-%S")
    return (
        task.file_transcription_options.default_output_file_name.replace(
            "{{ input_file_name }}", input_file_name
        )
        .replace("{{ task }}", task.transcription_options.task.value)
        .replace("{{ language }}", task.transcription_options.language or "")
        .replace("{{ model_type }}", task.transcription_options.model.model_type.value)
        .replace(
            "{{ model_size }}",
            task.transcription_options.model.whisper_model_size.value
            if task.transcription_options.model.whisper_model_size is not None
            else "",
        )
        .replace("{{ date_time }}", date_time_now)
        + f".{output_format.value}"
    )


def whisper_cpp_params(
    language: str,
    task: Task,
    word_level_timings: bool,
    print_realtime=False,
    print_progress=False,
):
    params = whisper_cpp.whisper_full_default_params(
        whisper_cpp.WHISPER_SAMPLING_GREEDY
    )
    params.print_realtime = print_realtime
    params.print_progress = print_progress
    params.language = whisper_cpp.String(language.encode("utf-8"))
    params.translate = task == Task.TRANSLATE
    params.max_len = ctypes.c_int(1)
    params.max_len = 1 if word_level_timings else 0
    params.token_timestamps = word_level_timings
    return params


class WhisperCpp:
    def __init__(self, model: str) -> None:
        self.ctx = whisper_cpp.whisper_init_from_file(model.encode("utf-8"))

    def transcribe(self, audio: Union[np.ndarray, str], params: Any):
        if isinstance(audio, str):
            audio = whisper.audio.load_audio(audio)

        logging.debug("Loaded audio with length = %s", len(audio))

        whisper_cpp_audio = audio.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        result = whisper_cpp.whisper_full(
            self.ctx, params, whisper_cpp_audio, len(audio)
        )
        if result != 0:
            raise Exception(f"Error from whisper.cpp: {result}")

        segments: List[Segment] = []

        n_segments = whisper_cpp.whisper_full_n_segments((self.ctx))
        for i in range(n_segments):
            txt = whisper_cpp.whisper_full_get_segment_text((self.ctx), i)
            t0 = whisper_cpp.whisper_full_get_segment_t0((self.ctx), i)
            t1 = whisper_cpp.whisper_full_get_segment_t1((self.ctx), i)

            segments.append(
                Segment(
                    start=t0 * 10,  # centisecond to ms
                    end=t1 * 10,  # centisecond to ms
                    text=txt.decode("utf-8"),
                )
            )

        return {
            "segments": segments,
            "text": "".join([segment.text for segment in segments]),
        }

    def __del__(self):
        whisper_cpp.whisper_free(self.ctx)
