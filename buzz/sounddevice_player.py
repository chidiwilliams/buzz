import logging
import subprocess
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from buzz.audio_devices import (
    refresh_audio_devices,
    register_stream,
    unregister_stream,
)
from buzz.ffmpeg_utils import find_ffmpeg, find_ffprobe
from buzz.pip_utils import subprocess_hide_window_kwargs


_find_ffmpeg = find_ffmpeg
_find_ffprobe = find_ffprobe

SAMPLE_RATE = 44100
CHANNELS = 2
FRAME_BYTES = CHANNELS * 2  # 16-bit samples
MIN_BUFFER_BYTES = 1 << 20


class AudioDecoder:
    """
    Decodes an audio/video file to 16-bit stereo samples with ffmpeg.
    Decoding a long file takes seconds, so another thread may cancel it.
    """

    def __init__(self, file_path: str,
                 on_progress: Optional[Callable[[float], None]] = None):
        """
        `on_progress` is called on the decoding thread with the fraction
        decoded so far, when the duration of the file is known.
        """
        self.file_path = file_path
        self._on_progress = on_progress
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def decode(self) -> Optional[np.ndarray]:
        """Returns the samples, or None if cancelled. Raises if ffmpeg fails."""
        # Raw samples through a pipe, as a WAV file in between costs a disk
        # write and read. int16 takes half the memory of float32, which for
        # a 30 minute file is 300 MB instead of 600 MB.
        args = [_find_ffmpeg(), "-nostdin", "-v", "error", "-i", self.file_path,
                "-vn", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
                "-f", "s16le", "pipe:1"]
        expected_bytes = self._expected_bytes()
        if self._start(args) is None:
            return None

        # Drain stderr alongside stdout, or ffmpeg blocks once that pipe fills
        stderr = []
        stderr_reader = threading.Thread(
            target=lambda: stderr.append(self._process.stderr.read()), daemon=True)
        stderr_reader.start()
        with self._process.stdout:
            samples = _read_samples(self._process.stdout, expected_bytes, self._on_progress)
        self._process.wait()
        stderr_reader.join()
        self._process.stderr.close()

        if self._cancelled:
            return None
        if self._process.returncode != 0:
            raise subprocess.CalledProcessError(
                self._process.returncode, args, stderr=b"".join(stderr))
        return samples

    def _start(self, args) -> Optional[subprocess.Popen]:
        """Starts a process that cancel() kills, or returns None if cancelled already."""
        with self._lock:
            if self._cancelled:
                return None
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **subprocess_hide_window_kwargs(),
            )
            return self._process

    def _expected_bytes(self) -> int:
        """Size of the decoded audio from the duration ffprobe reports, or 0 if unknown."""
        process = self._start(
            [_find_ffprobe(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", self.file_path])
        if process is None:
            return 0
        try:
            # A file on a network share that stopped responding can stall
            # ffprobe, in which case cancel() kills it
            stdout, _ = process.communicate(timeout=30)
            if process.returncode != 0:
                return 0
            duration_s = float(stdout.decode().strip())
        except Exception:
            if process.poll() is None:
                process.kill()
                process.communicate()
            logging.debug("Could not probe duration of %s", self.file_path, exc_info=True)
            return 0
        return int(duration_s * SAMPLE_RATE) * FRAME_BYTES

    def cancel(self):
        with self._lock:
            self._cancelled = True
            if self._process is not None and self._process.poll() is None:
                self._process.kill()


def _read_samples(stdout, expected_bytes: int,
                  on_progress: Optional[Callable[[float], None]] = None) -> np.ndarray:
    """
    Reads raw samples into one buffer sized up front, so the decoded audio is
    held in memory once. Collecting chunks and joining them, as
    Popen.communicate() does, needs twice that at the end.
    """
    # Some headroom, as the duration in the container is not always exact
    buffer = bytearray(max(expected_bytes + expected_bytes // 100, MIN_BUFFER_BYTES))
    size = 0
    while True:
        if size == len(buffer):
            # Longer than expected. Growing may copy the samples read so far.
            buffer.extend(bytes(len(buffer) // 2))
        read = stdout.readinto(memoryview(buffer)[size:])
        if not read:
            break
        size += read
        if on_progress is not None and expected_bytes > 0:
            on_progress(min(size / expected_bytes, 1.0))
    frames = size // FRAME_BYTES
    return np.frombuffer(buffer, dtype=np.int16, count=frames * CHANNELS).reshape(-1, CHANNELS)


class SounddevicePlayer:
    """Plays a numpy audio array through sounddevice with seek/pause/resume support."""

    def __init__(self, data: np.ndarray, samplerate: int):
        self.data = data
        self.samplerate = samplerate
        self._lock = threading.Lock()
        self._frame_pos = 0
        self._stream: Optional[sd.OutputStream] = None
        self._playing = False
        self._latency_frames = 0

    @property
    def position_ms(self) -> int:
        # ``_frame_pos`` advances when the callback *fills* the output buffer,
        # which runs ahead of what is actually audible by the device's output
        # latency. Report the audible position so callers comparing this against
        # another clock (e.g. QMediaPlayer in VideoPlayer) don't see a constant
        # offset and try to "correct" it.
        audible = max(0, self._frame_pos - self._latency_frames)
        return int(audible / self.samplerate * 1000)

    @property
    def duration_ms(self) -> int:
        return int(len(self.data) / self.samplerate * 1000)

    @property
    def is_playing(self) -> bool:
        return self._playing

    def _callback(self, outdata: np.ndarray, frames: int, time, status):
        with self._lock:
            remaining = len(self.data) - self._frame_pos
            if remaining <= 0:
                outdata[:] = 0
                self._playing = False
                raise sd.CallbackStop
            chunk = min(frames, remaining)
            outdata[:chunk] = self.data[self._frame_pos: self._frame_pos + chunk]
            if chunk < frames:
                outdata[chunk:] = 0
            self._frame_pos += chunk

    def _open_stream(self):
        channels = self.data.shape[1] if self.data.ndim == 2 else 1
        self._stream = sd.OutputStream(
            samplerate=self.samplerate,
            channels=channels,
            dtype=self.data.dtype.name,
            callback=self._callback,
            finished_callback=self._on_finished,
        )
        register_stream(self._stream)
        try:
            self._latency_frames = int(self._stream.latency * self.samplerate)
        except Exception:
            self._latency_frames = 0

    def _on_finished(self):
        self._playing = False

    def play(self):
        self._stop_stream()

        # Pick up devices that were connected, removed, or made default since
        # the last time we played, so we open the output the user is actually
        # listening to instead of a stale one.
        refresh_audio_devices()

        try:
            self._start_stream()
        except Exception:
            # The device can disappear between opening and starting it, e.g.
            # headphones dropping off. Re-read the devices and try once more
            # against whatever is the default output now.
            logging.warning("Could not start audio stream, retrying", exc_info=True)
            self._stop_stream()
            refresh_audio_devices()
            self._start_stream()

    def _start_stream(self):
        self._open_stream()
        self._playing = True
        self._stream.start()

    def pause(self):
        self._stop_stream()

    def resume(self):
        if not self._playing:
            self.play()

    def seek(self, position_ms: int):
        target = int(position_ms / 1000 * self.samplerate)
        target = max(0, min(target, len(self.data)))

        # Move the read cursor under the lock and let the running stream pick it
        # up on its next callback. Tearing the stream down and reopening the
        # device would drop audio for the duration of the device open, which is
        # audible as a stutter when seeks happen repeatedly.
        if self._playing and self._stream is not None:
            with self._lock:
                self._frame_pos = target
            return

        self._stop_stream()
        with self._lock:
            self._frame_pos = target

    def stop(self):
        self._stop_stream()
        with self._lock:
            self._frame_pos = 0

    def _stop_stream(self):
        self._playing = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                logging.debug("Error stopping sounddevice stream", exc_info=True)
            unregister_stream(self._stream)
            self._stream = None

    def close(self):
        self._stop_stream()


class AudioFilePlayer:
    """
    Decodes an audio/video file via ffmpeg and plays audio through sounddevice.
    Provides the same interface used by AudioPlayer and VideoPlayer.
    """

    def __init__(self, file_path: str, decoder: Optional[AudioDecoder] = None,
                 samples: Optional[np.ndarray] = None):
        """`samples` are already decoded ones, e.g. another player's, played without decoding again."""
        self._player: Optional[SounddevicePlayer] = None
        self._ready = False

        try:
            data = samples if samples is not None else (decoder or AudioDecoder(file_path)).decode()
            if data is not None:
                self._player = SounddevicePlayer(data, SAMPLE_RATE)
                self._ready = True
        except Exception:
            logging.error("AudioFilePlayer: failed to decode %s", file_path, exc_info=True)

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def samples(self) -> Optional[np.ndarray]:
        """The decoded samples, which other players of the same file can share."""
        return self._player.data if self._player else None

    @property
    def duration_ms(self) -> int:
        return self._player.duration_ms if self._player else 0

    @property
    def position_ms(self) -> int:
        return self._player.position_ms if self._player else 0

    @property
    def is_playing(self) -> bool:
        return self._player.is_playing if self._player else False

    def play(self):
        if self._player:
            self._player.play()

    def pause(self):
        if self._player:
            self._player.pause()

    def resume(self):
        if self._player:
            self._player.resume()

    def seek(self, position_ms: int):
        if self._player:
            self._player.seek(position_ms)

    def stop(self):
        if self._player:
            self._player.stop()

    def close(self):
        if self._player:
            self._player.close()
