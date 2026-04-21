import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Optional

import numpy as np


def _find_ffmpeg() -> str:
    import shutil
    path = shutil.which("ffmpeg")
    if path:
        return path
    for name in ("ffmpeg", "ffmpeg.exe"):
        p = os.path.join(getattr(sys, "_MEIPASS", ""), name)
        if os.path.exists(p):
            return p
    return "ffmpeg"


def _find_ffprobe() -> str:
    import shutil
    path = shutil.which("ffprobe")
    if path:
        return path
    for name in ("ffprobe", "ffprobe.exe"):
        p = os.path.join(getattr(sys, "_MEIPASS", ""), name)
        if os.path.exists(p):
            return p
    return "ffprobe"


def probe_video(file_path: str) -> dict:
    """Returns dict with duration_ms, fps, width, height, has_video."""
    ffprobe = _find_ffprobe()
    result = subprocess.run(
        [ffprobe, "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", file_path],
        capture_output=True, check=True, text=True,
    )
    info = json.loads(result.stdout)

    duration_s = float(info.get("format", {}).get("duration", 0) or 0)
    width = height = 0
    fps = 25.0
    has_video = False

    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            has_video = True
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            rfr = stream.get("r_frame_rate", "25/1")
            try:
                n, d = rfr.split("/")
                fps = float(n) / float(d)
            except Exception:
                fps = 25.0
            if not duration_s:
                duration_s = float(stream.get("duration", 0) or 0)
            break

    return {
        "duration_ms": int(duration_s * 1000),
        "fps": fps,
        "width": width,
        "height": height,
        "has_video": has_video,
    }


class FfmpegFrameReader:
    """
    Reads raw RGB24 video frames from a file via ffmpeg in a background thread.
    Frames are buffered as (timestamp_ms, ndarray) pairs.
    """

    MAX_BUFFER = 60

    def __init__(self, file_path: str, width: int, height: int, fps: float, start_ms: int = 0):
        self._file_path = file_path
        self._width = width
        self._height = height
        self._fps = fps
        self._frame_size = width * height * 3

        self._lock = threading.Lock()
        self._frames: deque = deque()
        self._start_ms = float(start_ms)
        self._done = False
        self._stop_event = threading.Event()
        self._proc: Optional[subprocess.Popen] = None

        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    @property
    def done(self) -> bool:
        with self._lock:
            return self._done and len(self._frames) == 0

    def _read_loop(self):
        ffmpeg = _find_ffmpeg()
        cmd = [
            ffmpeg,
            "-ss", str(self._start_ms / 1000.0),
            "-i", self._file_path,
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{self._width}x{self._height}",
            "-r", str(self._fps),
            "-an",
            "-",
        ]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            frame_ms = 1000.0 / self._fps
            pos = self._start_ms

            while not self._stop_event.is_set():
                # Throttle when buffer is full
                while not self._stop_event.is_set():
                    with self._lock:
                        if len(self._frames) < self.MAX_BUFFER:
                            break
                    time.sleep(0.005)

                if self._stop_event.is_set():
                    break

                raw = self._proc.stdout.read(self._frame_size)
                if len(raw) < self._frame_size:
                    with self._lock:
                        self._done = True
                    break

                arr = np.frombuffer(raw, dtype=np.uint8).reshape(
                    (self._height, self._width, 3)
                ).copy()
                with self._lock:
                    self._frames.append((pos, arr))
                pos += frame_ms

        except Exception:
            logging.debug("FfmpegFrameReader: read loop error", exc_info=True)
            with self._lock:
                self._done = True
        finally:
            if self._proc:
                try:
                    self._proc.stdout.close()
                    self._proc.kill()
                    self._proc.wait()
                except Exception:
                    pass

    def get_frame_for_position(self, position_ms: float) -> Optional[np.ndarray]:
        """Return best frame for position_ms, draining stale frames."""
        with self._lock:
            if not self._frames:
                return None

            frame_ms = 1000.0 / self._fps
            # Drain frames that are more than one frame period behind
            while len(self._frames) > 1:
                ts, _ = self._frames[0]
                if ts < position_ms - frame_ms:
                    self._frames.popleft()
                else:
                    break

            if not self._frames:
                return None

            ts, frame = self._frames[0]
            if ts <= position_ms + frame_ms:
                self._frames.popleft()
                return frame

            return None

    def stop(self):
        self._stop_event.set()
        if self._proc:
            try:
                self._proc.kill()
            except Exception:
                pass


class FfmpegVideoPlayer:
    """
    Provides software-decoded RGB video frames via ffmpeg.
    Avoids Qt's GPU video renderer which can produce green stripe artefacts.
    Call get_frame_for_position(position_ms) from a display timer.
    """

    def __init__(self, file_path: str):
        self._file_path = file_path
        self._reader: Optional[FfmpegFrameReader] = None
        self._last_frame: Optional[np.ndarray] = None

        try:
            info = probe_video(file_path)
        except Exception:
            logging.warning("FfmpegVideoPlayer: probe failed for %s", file_path, exc_info=True)
            info = {"duration_ms": 0, "fps": 25.0, "width": 0, "height": 0, "has_video": False}

        self.duration_ms: int = info["duration_ms"]
        self.fps: float = max(info["fps"], 1.0)
        self.width: int = info["width"]
        self.height: int = info["height"]
        self.has_video: bool = info["has_video"] and info["width"] > 0 and info["height"] > 0

    def start(self, position_ms: int = 0):
        if self._reader:
            self._reader.stop()
        if self.has_video:
            self._reader = FfmpegFrameReader(
                self._file_path, self.width, self.height, self.fps, position_ms
            )

    def seek(self, position_ms: int):
        self.start(position_ms)

    def get_frame_for_position(self, position_ms: int) -> Optional[np.ndarray]:
        if self._reader is None:
            return None
        frame = self._reader.get_frame_for_position(float(position_ms))
        if frame is not None:
            self._last_frame = frame
        return frame

    @property
    def last_frame(self) -> Optional[np.ndarray]:
        return self._last_frame

    def stop(self):
        if self._reader:
            self._reader.stop()
            self._reader = None

    def close(self):
        self.stop()
