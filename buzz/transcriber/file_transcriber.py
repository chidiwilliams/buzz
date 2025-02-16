import logging
import os
import sys
import subprocess
import shutil
import tempfile
from abc import abstractmethod
from typing import Optional, List

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from yt_dlp import YoutubeDL

from buzz.whisper_audio import SAMPLE_RATE
from buzz.transcriber.transcriber import (
    FileTranscriptionTask,
    get_output_file_path,
    Segment,
    OutputFormat,
)


class FileTranscriber(QObject):
    transcription_task: FileTranscriptionTask
    progress = pyqtSignal(tuple)  # (current, total)
    download_progress = pyqtSignal(float)
    completed = pyqtSignal(list)  # List[Segment]
    error = pyqtSignal(str)

    def __init__(self, task: FileTranscriptionTask, parent: Optional["QObject"] = None):
        super().__init__(parent)
        self.transcription_task = task

    @pyqtSlot()
    def run(self):
        if self.transcription_task.source == FileTranscriptionTask.Source.URL_IMPORT:
            temp_output_path = tempfile.mktemp()
            wav_file = temp_output_path + ".wav"

            cookiefile = os.getenv("BUZZ_DOWNLOAD_COOKIEFILE")

            options = {
                "format": "bestaudio/best",
                "progress_hooks": [self.on_download_progress],
                "outtmpl": temp_output_path,
                "logger": logging.getLogger(),
            }

            if cookiefile:
                options["cookiefile"] = cookiefile

            ydl = YoutubeDL(options)

            try:
                logging.debug(f"Downloading audio file from URL: {self.transcription_task.url}")
                ydl.download([self.transcription_task.url])
            except Exception as exc:
                logging.debug(f"Error downloading audio: {exc.msg}")
                self.error.emit(exc.msg)
                return

            cmd = [
                "ffmpeg",
                "-nostdin",
                "-threads", "0",
                "-i", temp_output_path,
                "-ac", "1",
                "-ar", str(SAMPLE_RATE),
                "-acodec", "pcm_s16le",
                "-loglevel", "panic",
                wav_file]

            if sys.platform == "win32":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
                result = subprocess.run(cmd, capture_output=True, startupinfo=si)
            else:
                result = subprocess.run(cmd, capture_output=True)

            if len(result.stderr):
                logging.warning(f"Error processing downloaded audio. Error: {result.stderr.decode()}")
                raise Exception(f"Error processing downloaded audio: {result.stderr.decode()}")

            self.transcription_task.file_path = wav_file
            logging.debug(f"Downloaded audio to file: {self.transcription_task.file_path}")

        try:
            segments = self.transcribe()
        except Exception as exc:
            logging.exception("")
            self.error.emit(str(exc))
            return

        for segment in segments:
            segment.text = segment.text.strip()

        self.completed.emit(segments)

        for (
            output_format
        ) in self.transcription_task.file_transcription_options.output_formats:
            default_path = get_output_file_path(
                file_path=self.transcription_task.file_path,
                output_format=output_format,
                language=self.transcription_task.transcription_options.language,
                output_directory=self.transcription_task.output_directory,
                model=self.transcription_task.transcription_options.model,
                task=self.transcription_task.transcription_options.task,
            )

            write_output(
                path=default_path, segments=segments, output_format=output_format
            )

        if self.transcription_task.source == FileTranscriptionTask.Source.FOLDER_WATCH:
            shutil.move(
                self.transcription_task.file_path,
                os.path.join(
                    self.transcription_task.output_directory,
                    os.path.basename(self.transcription_task.file_path),
                ),
            )

    def on_download_progress(self, data: dict):
        if data["status"] == "downloading":
            self.download_progress.emit(data["downloaded_bytes"] / data["total_bytes"])

    @abstractmethod
    def transcribe(self) -> List[Segment]:
        ...

    @abstractmethod
    def stop(self):
        ...


# TODO: Move to transcription service
def write_output(
    path: str,
    segments: List[Segment],
    output_format: OutputFormat,
    segment_key: str = 'text'
):
    logging.debug(
        "Writing transcription output, path = %s, output format = %s, number of segments = %s",
        path,
        output_format,
        len(segments),
    )

    with open(path, "w", encoding="utf-8") as file:
        if output_format == OutputFormat.TXT:
            combined_text = ""
            previous_end_time = None

            for segment in segments:
                if previous_end_time is not None and (segment.start - previous_end_time) >= 2000:
                    combined_text += "\n\n"
                combined_text += getattr(segment, segment_key).strip() + " "
                previous_end_time = segment.end

            file.write(combined_text)

        elif output_format == OutputFormat.VTT:
            file.write("WEBVTT\n\n")
            for segment in segments:
                file.write(
                    f"{to_timestamp(segment.start)} --> {to_timestamp(segment.end)}\n"
                )
                file.write(f"{getattr(segment, segment_key)}\n\n")

        elif output_format == OutputFormat.SRT:
            for i, segment in enumerate(segments):
                file.write(f"{i + 1}\n")
                file.write(
                    f'{to_timestamp(segment.start, ms_separator=",")} --> {to_timestamp(segment.end, ms_separator=",")}\n'
                )
                file.write(f"{getattr(segment, segment_key)}\n\n")

    logging.debug("Written transcription output")


def to_timestamp(ms: float, ms_separator=".") -> str:
    hr = int(ms / (1000 * 60 * 60))
    ms -= hr * (1000 * 60 * 60)
    min = int(ms / (1000 * 60))
    ms -= min * (1000 * 60)
    sec = int(ms / 1000)
    ms = int(ms - sec * 1000)
    return f"{hr:02d}:{min:02d}:{sec:02d}{ms_separator}{ms:03d}"
