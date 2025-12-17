import datetime
import json
import logging
import multiprocessing
import re
import os
import sys
import torch
import platform
import subprocess
from platformdirs import user_cache_dir
from multiprocessing.connection import Connection
from threading import Thread
from typing import Optional, List

import tqdm
from PyQt6.QtCore import QObject

from buzz import whisper_audio
from buzz.conn import pipe_stderr
from buzz.model_loader import ModelType, WhisperModelSize, map_language_to_mms
from buzz.transformers_whisper import TransformersTranscriber
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment, Task
from buzz.transcriber.whisper_cpp import WhisperCpp

import faster_whisper
import whisper
import stable_whisper
from stable_whisper import WhisperResult

PROGRESS_REGEX = re.compile(r"\d+(\.\d+)?%")


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
        self.recv_pipe = None
        self.send_pipe = None

    def transcribe(self) -> List[Segment]:
        time_started = datetime.datetime.now()
        logging.debug(
            "Starting whisper file transcription, task = %s", self.transcription_task
        )

        if torch.cuda.is_available():
            logging.debug(f"CUDA version detected: {torch.version.cuda}")

        self.recv_pipe, self.send_pipe = multiprocessing.Pipe(duplex=False)

        self.current_process = multiprocessing.Process(
            target=self.transcribe_whisper, args=(self.send_pipe, self.transcription_task)
        )
        if not self.stopped:
            self.current_process.start()
            self.started_process = True

        self.read_line_thread = Thread(target=self.read_line, args=(self.recv_pipe,))
        self.read_line_thread.start()

        # Only join the process if it was actually started
        if self.started_process:
            self.current_process.join()

        # Close the send pipe after process ends to signal read_line thread to stop
        # This prevents the read thread from blocking on recv() after the process is gone
        try:
            if self.send_pipe and not self.send_pipe.closed:
                self.send_pipe.close()
        except OSError:
            pass

        # Close the receive pipe to unblock the read_line thread
        try:
            if self.recv_pipe and not self.recv_pipe.closed:
                self.recv_pipe.close()
        except OSError:
            pass

        # Join read_line_thread with timeout to prevent hanging
        if self.read_line_thread and self.read_line_thread.is_alive():
            self.read_line_thread.join(timeout=3)
            if self.read_line_thread.is_alive():
                logging.warning("Read line thread didn't terminate gracefully in transcribe()")

        self.started_process = False

        logging.debug(
            "whisper process completed with code = %s, time taken = %s,"
            " number of segments = %s",
            self.current_process.exitcode,
            datetime.datetime.now() - time_started,
            len(self.segments),
        )

        if self.current_process.exitcode != 0:
            # Check if the process was terminated (likely due to cancellation)
            # Exit codes 124-128 are often used for termination signals
            if self.current_process.exitcode in [124, 125, 126, 127, 128, 130, 137, 143]:
                # Process was likely terminated, treat as cancellation
                logging.debug("Whisper process was terminated (exit code: %s), treating as cancellation", self.current_process.exitcode)
                raise Exception("Transcription was canceled")
            else:
                raise Exception("Unknown error")

        return self.segments

    @classmethod
    def transcribe_whisper(
        cls, stderr_conn: Connection, task: FileTranscriptionTask
    ) -> None:
        # Preload CUDA libraries in the subprocess - must be done before importing torch
        # This is needed because multiprocessing creates a fresh process without the main process's preloaded libraries
        from buzz import cuda_setup  # noqa: F401

        # Patch subprocess on Windows to prevent console window flash
        # This is needed because multiprocessing spawns a new process without the main process patches
        if sys.platform == "win32":
            import subprocess
            _original_run = subprocess.run
            _original_popen = subprocess.Popen

            def _patched_run(*args, **kwargs):
                if 'startupinfo' not in kwargs:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = subprocess.SW_HIDE
                    kwargs['startupinfo'] = si
                if 'creationflags' not in kwargs:
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                return _original_run(*args, **kwargs)

            class _PatchedPopen(subprocess.Popen):
                def __init__(self, *args, **kwargs):
                    if 'startupinfo' not in kwargs:
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        si.wShowWindow = subprocess.SW_HIDE
                        kwargs['startupinfo'] = si
                    if 'creationflags' not in kwargs:
                        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                    super().__init__(*args, **kwargs)

            subprocess.run = _patched_run
            subprocess.Popen = _PatchedPopen

        with pipe_stderr(stderr_conn):
            if task.transcription_options.model.model_type == ModelType.WHISPER_CPP:
                segments = cls.transcribe_whisper_cpp(task)
            elif task.transcription_options.model.model_type == ModelType.HUGGING_FACE:
                sys.stderr.write("0%\n")
                segments = cls.transcribe_hugging_face(task)
                sys.stderr.write("100%\n")
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
    def transcribe_whisper_cpp(cls, task: FileTranscriptionTask) -> List[Segment]:
        return WhisperCpp.transcribe(task)

    @classmethod
    def transcribe_hugging_face(cls, task: FileTranscriptionTask) -> List[Segment]:
        model = TransformersTranscriber(task.model_path)

        # Handle language - MMS uses ISO 639-3 codes, Whisper uses ISO 639-1
        if model.is_mms_model:
            language = map_language_to_mms(task.transcription_options.language or "eng")
            # MMS only supports transcription, ignore translation task
            effective_task = Task.TRANSCRIBE.value
            # MMS doesn't support word-level timestamps
            word_timestamps = False
        else:
            language = (
                task.transcription_options.language
                if task.transcription_options.language is not None
                else "en"
            )
            effective_task = task.transcription_options.task.value
            word_timestamps = task.transcription_options.word_level_timings

        result = model.transcribe(
            audio=task.file_path,
            language=language,
            task=effective_task,
            word_timestamps=word_timestamps,
        )
        return [
            Segment(
                start=int(segment.get("start") * 1000),
                end=int(segment.get("end") * 1000),
                text=segment.get("text"),
                translation=""
            )
            for segment in result.get("segments")
        ]

    @classmethod
    def transcribe_faster_whisper(cls, task: FileTranscriptionTask) -> List[Segment]:
        if task.transcription_options.model.whisper_model_size == WhisperModelSize.CUSTOM:
            model_size_or_path = task.transcription_options.model.hugging_face_model_id
        else:
            model_size_or_path = task.transcription_options.model.whisper_model_size.to_faster_whisper_model_size()

        model_root_dir = user_cache_dir("Buzz")
        model_root_dir = os.path.join(model_root_dir, "models")
        model_root_dir = os.getenv("BUZZ_MODEL_ROOT", model_root_dir)
        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")

        device = "auto"
        if torch.cuda.is_available() and torch.version.cuda < "12":
            logging.debug("Unsupported CUDA version (<12), using CPU")
            device = "cpu"

        if not torch.cuda.is_available():
            logging.debug("CUDA is not available, using CPU")
            device = "cpu"

        if force_cpu != "false":
            device = "cpu"

        # Check if user wants reduced GPU memory usage (int8 quantization)
        reduce_gpu_memory = os.getenv("BUZZ_REDUCE_GPU_MEMORY", "false") != "false"
        compute_type = "default"
        if reduce_gpu_memory:
            compute_type = "int8" if device == "cpu" else "int8_float16"
            logging.debug(f"Using {compute_type} compute type for reduced memory usage")

        model = faster_whisper.WhisperModel(
            model_size_or_path=model_size_or_path,
            download_root=model_root_dir,
            device=device,
            compute_type=compute_type,
            cpu_threads=(os.cpu_count() or 8)//2,
        )

        batched_model = faster_whisper.BatchedInferencePipeline(model=model)
        whisper_segments, info = batched_model.transcribe(
            audio=task.file_path,
            language=task.transcription_options.language,
            task=task.transcription_options.task.value,
            # Prevent crash on Windows https://github.com/SYSTRAN/faster-whisper/issues/71#issuecomment-1526263764
            temperature = 0 if platform.system() == "Windows" else task.transcription_options.temperature,
            initial_prompt=task.transcription_options.initial_prompt,
            word_timestamps=task.transcription_options.word_level_timings,
            no_speech_threshold=0.4,
            log_progress=True,
        )
        segments = []
        for segment in whisper_segments:
            # Segment will contain words if word-level timings is True
            if segment.words:
                for word in segment.words:
                    segments.append(
                        Segment(
                            start=int(word.start * 1000),
                            end=int(word.end * 1000),
                            text=word.word,
                            translation=""
                        )
                    )
            else:
                segments.append(
                    Segment(
                        start=int(segment.start * 1000),
                        end=int(segment.end * 1000),
                        text=segment.text,
                        translation=""
                    )
                )

        return segments

    @classmethod
    def transcribe_openai_whisper(cls, task: FileTranscriptionTask) -> List[Segment]:
        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        use_cuda = torch.cuda.is_available() and force_cpu == "false"

        device = "cuda" if use_cuda else "cpu"

        # Monkeypatch torch.load to use weights_only=False for PyTorch 2.6+
        # This is required for loading Whisper models with the newer PyTorch versions
        original_torch_load = torch.load
        def patched_torch_load(*args, **kwargs):
            kwargs.setdefault('weights_only', False)
            return original_torch_load(*args, **kwargs)

        torch.load = patched_torch_load
        try:
            model = whisper.load_model(task.model_path, device=device)
        finally:
            torch.load = original_torch_load

        if task.transcription_options.word_level_timings:
            stable_whisper.modify_model(model)
            result: WhisperResult = model.transcribe(
                audio=whisper_audio.load_audio(task.file_path),
                language=task.transcription_options.language,
                task=task.transcription_options.task.value,
                temperature=task.transcription_options.temperature,
                initial_prompt=task.transcription_options.initial_prompt,
                no_speech_threshold=0.4,
            )
            return [
                Segment(
                    start=int(word.start * 1000),
                    end=int(word.end * 1000),
                    text=word.word.strip(),
                    translation=""
                )
                for segment in result.segments
                for word in segment.words
            ]

        result: dict = model.transcribe(
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
                translation=""
            )
            for segment in segments
        ]

    def stop(self):
        self.stopped = True

        if self.started_process:
            self.current_process.terminate()

            if self.read_line_thread and self.read_line_thread.is_alive():
                self.read_line_thread.join(timeout=5)
                if self.read_line_thread.is_alive():
                    logging.warning("Read line thread still alive after 5s")

            self.current_process.join(timeout=10)
            if self.current_process.is_alive():
                logging.warning("Process didn't terminate gracefully, force killing")
                self.current_process.kill()
                self.current_process.join(timeout=5)

            try:
                if hasattr(self, 'send_pipe') and self.send_pipe:
                    self.send_pipe.close()
            except Exception as e:
                logging.debug(f"Error closing send_pipe: {e}")

            try:
                if hasattr(self, 'recv_pipe') and self.recv_pipe:
                    self.recv_pipe.close()
            except Exception as e:
                logging.debug(f"Error closing recv_pipe: {e}")

    def read_line(self, pipe: Connection):
        while True:
            try:
                line = pipe.recv().strip()

                # Uncomment to debug
                # print(f"*** DEBUG ***: {line}")

            except (EOFError, BrokenPipeError, ConnectionResetError, OSError):
                # Connection closed, broken, or process crashed (Windows RPC errors raise OSError)
                break
            except Exception as e:
                logging.debug(f"Error reading from pipe: {e}")
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
                        translation=""
                    )
                    for segment in segments_dict
                ]
                self.segments = segments
            else:
                try:
                    match = PROGRESS_REGEX.search(line)
                    if match is not None:
                        progress = int(match.group().strip("%"))
                        self.progress.emit((progress, 100))
                except ValueError:
                    logging.debug("whisper (stderr): %s", line)
                    continue
