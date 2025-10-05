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
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transformers_whisper import TransformersWhisper
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment, Task

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

        self.current_process.join()

        if self.current_process.exitcode != 0:
            self.send_pipe.close()

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
            raise Exception("Unknown error")

        return self.segments

    @classmethod
    def transcribe_whisper(
        cls, stderr_conn: Connection, task: FileTranscriptionTask
    ) -> None:
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
        # Get the directory where whisper-cli is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        whisper_cli_path = os.path.join(script_dir, "..", "whisper_cpp_vulkan", "whisper-cli")

        language = (
            task.transcription_options.language
            if task.transcription_options.language is not None
            else "en"
        )

        # Build the command
        cmd = [
            whisper_cli_path,
            "-m", task.model_path,
            "-l", language,
            "--print-progress",
            "--suppress-nst",
            "--output-json-full",
            "-f", task.file_path,
        ]

        # Add translate flag if needed
        if task.transcription_options.task == Task.TRANSLATE:
            cmd.append("--translate")

        # Force CPU if specified
        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        if force_cpu != "false":
            cmd.append("--no-gpu")

        # Run the whisper-cli process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Capture stderr for progress updates
        stderr_output = []
        while True:
            line = process.stderr.readline()
            if not line:
                break
            stderr_output.append(line.strip())
            # Progress is written to stderr
            sys.stderr.write(line)

        process.wait()

        if process.returncode != 0:
            raise Exception(f"whisper-cli failed with return code {process.returncode}")

        # Find and read the generated JSON file
        # whisper-cli generates: input_file.ext.json (e.g., file.mp3.json)
        json_output_path = f"{task.file_path}.json"

        try:
            # Read JSON with latin-1 to preserve raw bytes, then handle encoding per field
            # This is needed because whisper-cli can write invalid UTF-8 sequences for multi-byte characters
            with open(json_output_path, 'r', encoding='latin-1') as f:
                result = json.load(f)

            segments = []

            # Handle word-level timings
            if task.transcription_options.word_level_timings:
                # Extract word-level timestamps from tokens array
                # Combine tokens into words using similar logic as whisper_cpp.py
                transcription = result.get("transcription", [])
                for segment_data in transcription:
                    tokens = segment_data.get("tokens", [])

                    # Accumulate tokens into words
                    word_buffer = b""
                    word_start = 0
                    word_end = 0

                    def append_word(buffer: bytes, start: int, end: int):
                        """Try to decode and append a word segment, handling multi-byte UTF-8"""
                        if not buffer:
                            return True

                        # Try to decode as UTF-8
                        # https://github.com/ggerganov/whisper.cpp/issues/1798
                        try:
                            text = buffer.decode("utf-8").strip()
                            if text:
                                segments.append(
                                    Segment(
                                        start=start,
                                        end=end,
                                        text=text,
                                        translation=""
                                    )
                                )
                            return True
                        except UnicodeDecodeError:
                            # Multi-byte character is split, continue accumulating
                            return False

                    for token_data in tokens:
                        # Token text is read as latin-1, need to convert to bytes to get original data
                        token_text = token_data.get("text", "")

                        # Skip special tokens like [_TT_], [_BEG_]
                        if token_text.startswith("[_"):
                            continue

                        if not token_text:
                            continue

                        token_start = int(token_data.get("offsets", {}).get("from", 0))
                        token_end = int(token_data.get("offsets", {}).get("to", 0))

                        # Convert latin-1 string back to original bytes
                        # (latin-1 preserves byte values as code points)
                        token_bytes = token_text.encode("latin-1")

                        # Check if token starts with space - indicates new word
                        if token_bytes.startswith(b" ") and word_buffer:
                            # Save previous word
                            append_word(word_buffer, word_start, word_end)
                            # Start new word
                            word_buffer = token_bytes
                            word_start = token_start
                            word_end = token_end
                        elif token_bytes.startswith(b", "):
                            # Handle comma - save word with comma, then start new word
                            word_buffer += b","
                            append_word(word_buffer, word_start, word_end)
                            word_buffer = token_bytes.lstrip(b",")
                            word_start = token_start
                            word_end = token_end
                        else:
                            # Accumulate token into current word
                            if not word_buffer:
                                word_start = token_start
                            word_buffer += token_bytes
                            word_end = token_end

                    # Add the last word
                    append_word(word_buffer, word_start, word_end)
            else:
                # Use segment-level timestamps
                transcription = result.get("transcription", [])
                for segment_data in transcription:
                    # Segment text is also read as latin-1, convert back to UTF-8
                    segment_text_latin1 = segment_data.get("text", "")
                    try:
                        # Convert latin-1 string to bytes, then decode as UTF-8
                        segment_text = segment_text_latin1.encode("latin-1").decode("utf-8").strip()
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        # If conversion fails, use the original text
                        segment_text = segment_text_latin1.strip()

                    segments.append(
                        Segment(
                            start=int(segment_data.get("offsets", {}).get("from", 0)),
                            end=int(segment_data.get("offsets", {}).get("to", 0)),
                            text=segment_text,
                            translation=""
                        )
                    )

            return segments
        finally:
            # Clean up the generated JSON file
            if os.path.exists(json_output_path):
                try:
                    os.remove(json_output_path)
                except Exception as e:
                    logging.warning(f"Failed to remove JSON output file {json_output_path}: {e}")

    @classmethod
    def transcribe_hugging_face(cls, task: FileTranscriptionTask) -> List[Segment]:
        model = TransformersWhisper(task.model_path)
        language = (
            task.transcription_options.language
            if task.transcription_options.language is not None
            else "en"
        )
        result = model.transcribe(
            audio=task.file_path,
            language=language,
            task=task.transcription_options.task.value,
            word_timestamps=task.transcription_options.word_level_timings,
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

        model = faster_whisper.WhisperModel(
            model_size_or_path=model_size_or_path,
            download_root=model_root_dir,
            device=device,
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
        model = whisper.load_model(task.model_path, device=device)

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
            # Use timeout to avoid hanging indefinitely
            self.current_process.join(timeout=5)
            if self.current_process.is_alive():
                logging.warning("Process didn't terminate gracefully, force killing")
                self.current_process.kill()
                self.current_process.join(timeout=2)
            
            # Close pipes to unblock the read_line thread
            try:
                if hasattr(self, 'send_pipe'):
                    self.send_pipe.close()
                if hasattr(self, 'recv_pipe'):
                    self.recv_pipe.close()
            except Exception as e:
                logging.debug(f"Error closing pipes: {e}")
            
            # Join read_line_thread with timeout to prevent hanging
            if self.read_line_thread and self.read_line_thread.is_alive():
                self.read_line_thread.join(timeout=3)
                if self.read_line_thread.is_alive():
                    logging.warning("Read line thread didn't terminate gracefully")

    def read_line(self, pipe: Connection):
        while True:
            try:
                line = pipe.recv().strip()

                # Uncomment to debug
                # print(f"*** DEBUG ***: {line}")

            except (EOFError, BrokenPipeError, ConnectionResetError):  # Connection closed or broken
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
