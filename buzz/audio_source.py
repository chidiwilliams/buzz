import abc
import logging
import os
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from buzz.assets import APP_BASE_DIR


SCREEN_AUDIO_HELPER_NAME = "buzz-screen-audio"


def get_screen_audio_helper_path() -> Optional[str]:
    """Locate the buzz-screen-audio helper binary.

    Follows the same two-level resolution pattern used for whisper-cli
    in recording_transcriber.py and whisper_cpp.py.
    """
    path = os.path.join(APP_BASE_DIR, "whisper_cpp", SCREEN_AUDIO_HELPER_NAME)
    if os.path.isfile(path):
        return path
    path = os.path.join(APP_BASE_DIR, "buzz", "whisper_cpp", SCREEN_AUDIO_HELPER_NAME)
    if os.path.isfile(path):
        return path
    return None


@dataclass
class AudioSourceConfig:
    """Describes which audio source a RecordingTranscriber should use.

    Passed from the widget to the transcriber so that the actual AudioSource
    is created inside ``RecordingTranscriber.start()`` where
    ``stream_callback`` is available.
    """

    source_type: str  # "sounddevice" or "screen_capture"
    device_index: Optional[int] = None  # For sounddevice
    helper_path: Optional[str] = None  # For screen_capture


class AudioSource(abc.ABC):
    """Abstract audio source providing a context-manager interface.

    Matches how ``sounddevice.InputStream`` is used in
    ``RecordingTranscriber.start()`` — enter starts audio, exit stops it.
    While active, the source calls *callback(in_data, frame_count,
    time_info, status)* with numpy arrays in the same shape that
    sounddevice produces: ``(N, 1)`` float32.
    """

    @abc.abstractmethod
    def __enter__(self):
        pass

    @abc.abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class SoundDeviceAudioSource(AudioSource):
    """Thin wrapper around ``sounddevice.InputStream``.

    Drop-in replacement for the previous inline construction so
    existing mic recording behaviour is unchanged.
    """

    def __init__(self, sounddevice_module, samplerate: int,
                 device: Optional[int], dtype: str, channels: int,
                 callback: Callable):
        self._stream = sounddevice_module.InputStream(
            samplerate=samplerate,
            device=device,
            dtype=dtype,
            channels=channels,
            callback=callback,
        )

    def __enter__(self):
        self._stream.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._stream.__exit__(exc_type, exc_val, exc_tb)


class ScreenCaptureAudioSource(AudioSource):
    """Reads raw float32 mono 16 kHz PCM from the Swift helper's stdout.

    The helper binary (``buzz-screen-audio``) uses ScreenCaptureKit to
    capture system audio, downsamples to 16 kHz mono float32, and writes
    raw samples to stdout.  This class spawns the helper, reads its
    output in a daemon thread, and feeds chunks to the same *callback*
    signature that ``sounddevice.InputStream`` uses.
    """

    def __init__(self, helper_path: str, sample_rate: int,
                 callback: Callable):
        self._helper_path = helper_path
        self._sample_rate = sample_rate
        self._callback = callback
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def __enter__(self):
        self._stop_event.clear()
        self._process = subprocess.Popen(
            [self._helper_path, "--sample-rate", str(self._sample_rate)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self._reader_thread = threading.Thread(
            target=self._read_loop, daemon=True, name="screen-capture-reader"
        )
        self._reader_thread.start()
        return self

    def _read_loop(self):
        """Continuously read raw PCM from the helper and invoke the callback."""
        # Read in ~100 ms chunks (matches typical sounddevice callback cadence)
        chunk_samples = self._sample_rate // 10
        chunk_bytes = chunk_samples * 4  # float32 = 4 bytes per sample

        try:
            while not self._stop_event.is_set():
                data = self._process.stdout.read(chunk_bytes)
                if not data:
                    break
                # Pad the last partial chunk with silence if needed
                if len(data) < chunk_bytes:
                    data = data + b"\x00" * (chunk_bytes - len(data))
                samples = np.frombuffer(data, dtype=np.float32).copy()
                # Reshape to (N, 1) to match sounddevice convention
                samples = samples.reshape(-1, 1)
                self._callback(samples, len(samples), None, None)
        except Exception:
            logging.exception("Error reading from screen capture helper")

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop_event.set()
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=5)
        return False
