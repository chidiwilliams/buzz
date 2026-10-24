import logging
import os
import sys
import subprocess
import shutil
import tempfile
import threading
from abc import abstractmethod
from typing import Any, Optional, List
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadCancelled

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


def _downloaded_file_path(info: Any) -> Path:
    """Return the actual file path reported by yt-dlp after downloading."""
    candidates = []

    if info is not None:
        filepath = info.get("filepath")
        if filepath:
            candidates.append(filepath)

        for download in info.get("requested_downloads") or []:
            filepath = download.get("filepath")
            if filepath:
                candidates.append(filepath)

    for candidate in candidates:
        path = Path(candidate).resolve()
        if path.is_file():
            return path

    reported_path = candidates[0] if candidates else "<no filepath reported>"
    raise FileNotFoundError(f"yt-dlp output does not exist: {reported_path}")


DOWNLOAD_CANCELED_MESSAGE = "Download canceled"


class FileTranscriber(QObject):
    transcription_task: FileTranscriptionTask
    progress = pyqtSignal(tuple)  # (current, total)
    download_progress = pyqtSignal(float)
    completed = pyqtSignal(list)  # List[Segment]
    error = pyqtSignal(str)

    def __init__(self, task: FileTranscriptionTask, parent: Optional["QObject"] = None):
        super().__init__(parent)
        self.transcription_task = task
        self._download_canceled = threading.Event()
        self._download_process: Optional[subprocess.Popen] = None

    @pyqtSlot()
    def download(self):
        """Prepare URL audio in a thread that stop() can cancel."""
        try:
            if not self._download_from_url():
                return
        except Exception as exc:
            logging.exception("Failed to prepare URL audio")
            self.error.emit(str(exc))
            return
        self.completed.emit([])

    @pyqtSlot()
    def run(self):
        """Transcribe ``task.file_path``. URL tasks must run download() first."""
        try:
            segments = self.transcribe()
        except Exception as exc:
            logging.exception("")
            self.error.emit(str(exc))
            return

        for segment in segments:
            segment.text = segment.text.strip()

        if self.transcription_task.identify_speakers:
            segments = self._identify_speakers(segments)

        # Move/delete the watched source file before announcing completion so
        # the task carries the final file path when the transcription is saved.
        if self.transcription_task.source == FileTranscriptionTask.Source.FOLDER_WATCH:
            try:
                self._handle_folder_watch()
            except OSError:
                logging.exception("Failed to move or delete folder watch source file")

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
                display_name=self.transcription_task.display_name,
            )

            write_output(
                path=default_path, segments=segments, output_format=output_format
            )

    def _identify_speakers(self, segments: List[Segment]) -> List[Segment]:
        """Add automatic speaker labels before the transcription is exported."""
        from buzz.transcriber.speaker_identifier import identify_speakers

        logging.debug(
            "Identifying speakers for %s", self.transcription_task.file_path
        )

        return identify_speakers(
            file_path=self.transcription_task.file_path,
            segments=segments,
            language=self.transcription_task.transcription_options.language,
            diarizer=self.transcription_task.speaker_diarizer,
            num_speakers=self.transcription_task.speaker_count,
            merge_speaker_sentences=self.transcription_task.merge_speaker_sentences,
        )

    def _download_from_url(self) -> bool:
        cookiefile = os.getenv("BUZZ_DOWNLOAD_COOKIEFILE")

        temp_dir = Path(tempfile.mkdtemp()).resolve()
        # Never derive a working path from the media title. In particular,
        # yt-dlp normalizes trailing dots and spaces differently on Windows.
        download_template = str(temp_dir / "source.%(ext)s")
        wav_file = temp_dir / "audio.wav"

        options = {
            "format": "bestaudio/best",
            "progress_hooks": [self.on_download_progress],
            "outtmpl": download_template,
            "logger": logging.getLogger(),
        }

        if cookiefile:
            options["cookiefile"] = cookiefile

        try:
            logging.debug(f"Downloading audio file from URL: {self.transcription_task.url}")
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(self.transcription_task.url, download=True)
            downloaded_file = _downloaded_file_path(info)
            title = info.get("title")
            if title:
                self.transcription_task.display_name = title
        except Exception as exc:
            if self._download_canceled.is_set():
                self.error.emit(DOWNLOAD_CANCELED_MESSAGE)
                return False
            message = getattr(exc, "msg", str(exc))
            logging.debug(f"Error downloading audio: {message}")
            self.error.emit(message)
            return False

        cmd = [
            "ffmpeg",
            "-nostdin",
            "-threads", "0",
            "-i", str(downloaded_file),
            "-ac", "1",
            "-ar", str(whisper_audio.SAMPLE_RATE),
            "-acodec", "pcm_s16le",
            "-loglevel", "panic",
            str(wav_file)
        ]

        popen_kwargs = {}
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            popen_kwargs = {
                "startupinfo": si,
                "env": app_env,
                "creationflags": subprocess.CREATE_NO_WINDOW,
            }

        # Popen rather than run() so stop() can kill ffmpeg mid-conversion.
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen_kwargs
        )
        self._download_process = process
        # stop() may have run before the process was published above.
        if self._download_canceled.is_set():
            process.kill()
        _, stderr = process.communicate()
        self._download_process = None

        if self._download_canceled.is_set():
            self.error.emit(DOWNLOAD_CANCELED_MESSAGE)
            return False

        if process.returncode != 0:
            error = stderr.decode("utf-8", errors="replace")
            if not error:
                error = f"ffmpeg exited with code {process.returncode}"
            message = f"Error processing downloaded audio: {error}"
            logging.warning(message)
            self.error.emit(message)
            return False

        if not wav_file.is_file():
            message = f"FFmpeg output does not exist: {wav_file}"
            logging.warning(message)
            self.error.emit(message)
            return False

        self.transcription_task.file_path = str(wav_file)
        # A path kept from an earlier run's speech extraction points at the
        # previous download, not this one.
        self.transcription_task.original_file_path = None
        logging.debug(f"Downloaded audio to file: {self.transcription_task.file_path}")
        return True

    def _handle_folder_watch(self):
        source_path = (
            self.transcription_task.original_file_path
            or self.transcription_task.file_path
        )
        if not source_path or not os.path.exists(source_path):
            return

        if self.transcription_task.delete_source_file:
            os.remove(source_path)
            return

        destination = os.path.join(
            self.transcription_task.output_directory,
            os.path.basename(source_path),
        )

        # The output directory may be the input directory, in which case there
        # is nothing to move.
        if not os.path.exists(destination) or not os.path.samefile(
            source_path, destination
        ):
            shutil.move(source_path, destination)

        # Point the task at the new location so the transcription keeps a
        # working path and the audio stays playable.
        self.transcription_task.file_path = destination
        self.transcription_task.original_file_path = destination

    def on_download_progress(self, data: dict):
        # yt-dlp calls this hook throughout the download and re-raises
        # DownloadCancelled out of extract_info, which aborts it cleanly.
        if self._download_canceled.is_set():
            raise DownloadCancelled()

        if data.get("status") != "downloading":
            return

        # Segmented downloads (DASH, HLS) often report no exact size, only an
        # estimate, and sometimes neither on the first fragments.
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        downloaded = data.get("downloaded_bytes")
        if not total or downloaded is None:
            return

        self.download_progress.emit(min(downloaded / total, 1.0))

    @abstractmethod
    def transcribe(self) -> List[Segment]:
        ...

    def stop(self):
        """Cancel a URL download in progress. Subclasses that override this
        must call super().stop()."""
        self._download_canceled.set()
        process = self._download_process
        if process is not None and process.poll() is None:
            process.kill()


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
        def segment_content(segment):
            content = getattr(segment, segment_key).strip()
            speaker = getattr(segment, "speaker", "").strip()
            return f"{speaker}: {content}" if speaker else content

        if output_format == OutputFormat.TXT:
            combined_text = ""
            previous_end_time = None

            paragraph_split_time = int(os.getenv("BUZZ_PARAGRAPH_SPLIT_TIME", "2000"))
            
            for segment in segments:
                if previous_end_time is not None and (segment.start - previous_end_time) >= paragraph_split_time:
                    combined_text += "\n\n"
                combined_text += segment_content(segment) + " "
                previous_end_time = segment.end

            file.write(combined_text)

        elif output_format == OutputFormat.VTT:
            file.write("WEBVTT\n\n")
            for segment in segments:
                file.write(
                    f"{to_timestamp(segment.start)} --> {to_timestamp(segment.end)}\n"
                )
                file.write(f"{segment_content(segment)}\n\n")

        elif output_format == OutputFormat.SRT:
            for i, segment in enumerate(segments):
                file.write(f"{i + 1}\n")
                file.write(
                    f'{to_timestamp(segment.start, ms_separator=",")} --> {to_timestamp(segment.end, ms_separator=",")}\n'
                )
                file.write(f"{segment_content(segment)}\n\n")

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
