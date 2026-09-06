import logging
import os
import subprocess
import tempfile
import threading
import wave
from typing import Optional

import numpy as np
import sounddevice as sd

from buzz.ffmpeg_utils import find_ffmpeg
from buzz.pip_utils import subprocess_hide_window_kwargs


_find_ffmpeg = find_ffmpeg


def decode_audio_to_wav(input_path: str, output_wav: str) -> None:
    ffmpeg = _find_ffmpeg()
    subprocess.run(
        [ffmpeg, "-y", "-i", input_path, "-vn", "-ar", "44100", "-ac", "2",
         "-f", "wav", output_wav],
        capture_output=True,
        check=True,
        **subprocess_hide_window_kwargs(),
    )


def load_wav(wav_path: str):
    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
    data = np.frombuffer(raw, dtype=dtype).astype(np.float32) / np.iinfo(dtype).max
    if n_channels > 1:
        data = data.reshape(-1, n_channels)
    return data, framerate


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
            dtype="float32",
            callback=self._callback,
            finished_callback=self._on_finished,
        )
        try:
            self._latency_frames = int(self._stream.latency * self.samplerate)
        except Exception:
            self._latency_frames = 0

    def _on_finished(self):
        self._playing = False

    def play(self):
        self._stop_stream()
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
            self._stream = None

    def close(self):
        self._stop_stream()


class AudioFilePlayer:
    """
    Decodes an audio/video file via ffmpeg and plays audio through sounddevice.
    Provides the same interface used by AudioPlayer and VideoPlayer.
    """

    def __init__(self, file_path: str):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._wav_path = os.path.join(self._tmp_dir.name, "audio.wav")
        self._player: Optional[SounddevicePlayer] = None
        self._ready = False

        try:
            decode_audio_to_wav(file_path, self._wav_path)
            data, samplerate = load_wav(self._wav_path)
            self._player = SounddevicePlayer(data, samplerate)
            self._ready = True
        except Exception:
            logging.error("AudioFilePlayer: failed to decode %s", file_path, exc_info=True)

    @property
    def ready(self) -> bool:
        return self._ready

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
        try:
            self._tmp_dir.cleanup()
        except Exception:
            pass
