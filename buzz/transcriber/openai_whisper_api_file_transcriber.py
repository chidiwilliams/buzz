import logging
import math
import os
import sys
import subprocess
import tempfile
from typing import Optional, List

from PyQt6.QtCore import QObject
from openai import OpenAI

from buzz.settings.settings import Settings
from buzz.model_loader import get_custom_api_whisper_model
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment, Task


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
        logging.debug("Will use whisper API on %s, %s",
                      custom_openai_base_url, self.whisper_api_model)

    def transcribe(self) -> List[Segment]:
        logging.debug(
            "Starting OpenAI Whisper API file transcription, file path = %s, task = %s",
            self.transcription_task.file_path,
            self.task,
        )

        mp3_file = tempfile.mktemp() + ".mp3"

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
            result = subprocess.run(cmd, capture_output=True, startupinfo=si)
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
                subprocess.run(cmd, capture_output=True, check=True, startupinfo=si).stdout.decode("utf-8")
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
                subprocess.run(cmd, capture_output=True, check=True, startupinfo=si)
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

    def get_segments_for_file(self, file: str, offset_ms: int = 0):
        with open(file, "rb") as file:
            options = {
                "model": self.whisper_api_model,
                "file": file,
                "response_format": "verbose_json",
                "prompt": self.transcription_task.transcription_options.initial_prompt,
            }
            transcript = (
                self.openai_client.audio.transcriptions.create(
                    **options,
                    language=self.transcription_task.transcription_options.language,
                )
                if self.transcription_task.transcription_options.task == Task.TRANSCRIBE
                else self.openai_client.audio.translations.create(**options)
            )

            return [
                Segment(
                    int(segment["start"] * 1000 + offset_ms),
                    int(segment["end"] * 1000 + offset_ms),
                    segment["text"],
                )
                for segment in transcript.model_extra["segments"]
            ]

    def stop(self):
        pass
