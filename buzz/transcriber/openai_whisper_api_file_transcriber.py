import logging
import math
import os
import sys
import subprocess
import tempfile

from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import QObject
from openai import OpenAI

from buzz.settings.settings import Settings
from buzz.model_loader import get_custom_api_whisper_model
from buzz.transcriber.file_transcriber import FileTranscriber, app_env
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment, Task
from buzz.transcriber.whisper_cpp import append_segment


class OpenAIWhisperAPIFileTranscriber(FileTranscriber):
    def __init__(self, task: FileTranscriptionTask, parent: Optional["QObject"] = None):
        super().__init__(task=task, parent=parent)
        settings = Settings()
        custom_openai_base_url = settings.value(
            key=Settings.Key.CUSTOM_OPENAI_BASE_URL, default_value=""
        )
        self.task = task.transcription_options.task
        self.openai_client = OpenAI(
            api_key=self.transcription_task.transcription_options.openai_access_token,
            base_url=custom_openai_base_url if custom_openai_base_url else None
        )
        self.whisper_api_model = get_custom_api_whisper_model(custom_openai_base_url)
        self.word_level_timings = self.transcription_task.transcription_options.word_level_timings
        logging.debug("Will use whisper API on %s, %s",
                      custom_openai_base_url, self.whisper_api_model)

    def transcribe(self) -> List[Segment]:
        logging.debug(
            "Starting OpenAI Whisper API file transcription, file path = %s, task = %s",
            self.transcription_task.file_path,
            self.task,
        )

        mp3_file = tempfile.mktemp() + ".mp3"
        mp3_file = str(Path(mp3_file).resolve())

        cmd = [
            "ffmpeg",
            "-threads", "0",
            "-loglevel", "panic",
            "-i", self.transcription_task.file_path, mp3_file
        ]

        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            result = subprocess.run(cmd, capture_output=True, startupinfo=si, env=app_env)
        else:
            result = subprocess.run(cmd, capture_output=True)

        if result.returncode != 0:
            logging.warning(f"FFMPEG audio load warning. Process return code was not zero: {result.returncode}")

        if len(result.stderr):
            logging.warning(f"FFMPEG audio load error. Error: {result.stderr.decode()}")
            raise Exception(f"FFMPEG Failed to load audio: {result.stderr.decode()}")

        # fmt: off
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            mp3_file,
        ]

        # fmt: on
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            duration_secs = float(
                subprocess.run(cmd, capture_output=True, check=True, startupinfo=si, env=app_env).stdout.decode("utf-8")
            )
        else:
            duration_secs = float(
                subprocess.run(cmd, capture_output=True, check=True).stdout.decode("utf-8")
            )

        total_size = os.path.getsize(mp3_file)
        max_chunk_size = 25 * 1024 * 1024

        self.progress.emit((0, 100))

        if total_size < max_chunk_size:
            return self.get_segments_for_file(mp3_file)

        # If the file is larger than 25MB, split into chunks
        # and transcribe each chunk separately
        num_chunks = math.ceil(total_size / max_chunk_size)
        chunk_duration = duration_secs / num_chunks

        segments = []

        for i in range(num_chunks):
            chunk_start = i * chunk_duration
            chunk_end = min((i + 1) * chunk_duration, duration_secs)

            chunk_file = tempfile.mktemp() + ".mp3"
            chunk_file = str(Path(chunk_file).resolve())

            # fmt: off
            cmd = [
                "ffmpeg",
                "-i", mp3_file,
                "-ss", str(chunk_start),
                "-to", str(chunk_end),
                "-c", "copy",
                chunk_file,
            ]
            # fmt: on
            if sys.platform == "win32":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
                subprocess.run(cmd, capture_output=True, check=True, startupinfo=si, env=app_env)
            else:
                subprocess.run(cmd, capture_output=True, check=True)

            logging.debug('Created chunk file "%s"', chunk_file)

            segments.extend(
                self.get_segments_for_file(
                    chunk_file, offset_ms=int(chunk_start * 1000)
                )
            )
            os.remove(chunk_file)
            self.progress.emit((i + 1, num_chunks))

        return segments

    @staticmethod
    def get_value(segment, key):
        if hasattr(segment, key):
            return getattr(segment, key)
        return segment[key]

    def get_segments_for_file(self, file: str, offset_ms: int = 0):
        with open(file, "rb") as file:
            options = {
                "model": self.whisper_api_model,
                "file": file,
                "response_format": "verbose_json",
                "prompt": self.transcription_task.transcription_options.initial_prompt,
            }

            if self.word_level_timings:
                options["timestamp_granularities"] = ["word"]

            transcript = (
                self.openai_client.audio.transcriptions.create(
                    **options,
                    language=self.transcription_task.transcription_options.language,
                )
                if self.transcription_task.transcription_options.task == Task.TRANSCRIBE
                else self.openai_client.audio.translations.create(**options)
            )

            segments = getattr(transcript, "segments", None)

            words = getattr(transcript, "words", None)
            if words is None and "words" in transcript.model_extra:
                words = transcript.model_extra["words"]

            if segments is None:
                if "segments" in transcript.model_extra:
                    segments = transcript.model_extra["segments"]
                else:
                    segments = [{"words": words}]

            result_segments = []
            if self.word_level_timings:

                # Detect response from whisper.cpp API
                first_segment = segments[0] if segments else None
                is_whisper_cpp = (first_segment and hasattr(first_segment, "tokens")
                                  and hasattr(first_segment, "avg_logprob") and hasattr(first_segment, "no_speech_prob"))

                if is_whisper_cpp:
                    txt_buffer = b''
                    txt_start = 0
                    txt_end = 0

                    for segment in segments:
                        for word in self.get_value(segment, "words"):

                            txt = self.get_value(word, "word").encode("utf-8")
                            start = self.get_value(word, "start")
                            end = self.get_value(word, "end")

                            if txt.startswith(b' ') and append_segment(result_segments, txt_buffer, txt_start, txt_end):
                                txt_buffer = txt
                                txt_start = start
                                txt_end = end
                                continue

                            if txt.startswith(b', '):
                                txt_buffer += b','
                                append_segment(result_segments, txt_buffer, txt_start, txt_end)
                                txt_buffer = txt.lstrip(b',')
                                txt_start = start
                                txt_end = end
                                continue

                            txt_buffer += txt
                            txt_end = end

                        # Append the last segment
                        append_segment(result_segments, txt_buffer, txt_start, txt_end)

                else:
                    for segment in segments:
                        for word in self.get_value(segment, "words"):
                            result_segments.append(
                                Segment(
                                    int(self.get_value(word, "start") * 1000 + offset_ms),
                                    int(self.get_value(word, "end") * 1000 + offset_ms),
                                    self.get_value(word, "word"),
                                )
                            )
            else:
                result_segments = [
                    Segment(
                        int(self.get_value(segment, "start") * 1000 + offset_ms),
                        int(self.get_value(segment,"end") * 1000 + offset_ms),
                        self.get_value(segment,"text"),
                    )
                    for segment in segments
                ]

            return result_segments

    def stop(self):
        pass
