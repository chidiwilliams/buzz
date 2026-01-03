import logging
import os
import sys
import subprocess
import shutil
import tempfile
from abc import abstractmethod
from typing import Optional, List
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from yt_dlp import YoutubeDL

from buzz import whisper_audio
from buzz.assets import APP_BASE_DIR
from buzz.transcriber.transcriber import (
    FileTranscriptionTask,
    get_output_file_path,
    Segment,
    OutputFormat,
)

app_env = os.environ.copy()
app_env['PATH'] = os.pathsep.join([os.path.join(APP_BASE_DIR, "_internal")] + [app_env['PATH']])


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
            cookiefile = os.getenv("BUZZ_DOWNLOAD_COOKIEFILE")

            # First extract info to get the video title
            extract_options = {
                "logger": logging.getLogger(),
            }
            if cookiefile:
                extract_options["cookiefile"] = cookiefile

            try:
                with YoutubeDL(extract_options) as ydl_info:
                    info = ydl_info.extract_info(self.transcription_task.url, download=False)
                    video_title = info.get("title", "audio")
            except Exception as exc:
                logging.debug(f"Error extracting video info: {exc}")
                video_title = "audio"

            # Sanitize title for use as filename
            video_title = YoutubeDL.sanitize_info({"title": video_title})["title"]
            # Remove characters that are problematic in filenames
            for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
                video_title = video_title.replace(char, '_')

            # Create temp directory and use video title as filename
            temp_dir = tempfile.mkdtemp()
            temp_output_path = os.path.join(temp_dir, video_title)
            wav_file = temp_output_path + ".wav"
            wav_file = str(Path(wav_file).resolve())

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
                "-ar", str(whisper_audio.SAMPLE_RATE),
                "-acodec", "pcm_s16le",
                "-loglevel", "panic",
                wav_file
            ]

            if sys.platform == "win32":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    startupinfo=si,
                    env=app_env,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
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
            # Use original_file_path if available (before speech extraction changed file_path)
            source_path = (
                self.transcription_task.original_file_path
                or self.transcription_task.file_path
            )
            if source_path and os.path.exists(source_path):
                shutil.move(
                    source_path,
                    os.path.join(
                        self.transcription_task.output_directory,
                        os.path.basename(source_path),
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

    with open(os.fsencode(path), "w", encoding="utf-8") as file:
        if output_format == OutputFormat.TXT:
            combined_text = ""
            previous_end_time = None

            paragraph_split_time = int(os.getenv("BUZZ_PARAGRAPH_SPLIT_TIME", "2000"))
            
            for segment in segments:
                if previous_end_time is not None and (segment.start - previous_end_time) >= paragraph_split_time:
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

# To detect when transcription source is a video
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".ogm", ".wmv"}

def is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS
