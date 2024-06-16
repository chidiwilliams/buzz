import os
import time
import logging
from threading import Thread
from typing import Callable, Any
from unittest.mock import MagicMock

import numpy as np
import sounddevice

from buzz import whisper_audio

mock_query_devices = [
    {
        "name": "Background Music",
        "index": 0,
        "hostapi": 0,
        "max_input_channels": 2,
        "max_output_channels": 2,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.008,
        "default_high_input_latency": 0.1,
        "default_high_output_latency": 0.064,
        "default_samplerate": 8000.0,
    },
    {
        "name": "Background Music (UI Sounds)",
        "index": 1,
        "hostapi": 0,
        "max_input_channels": 2,
        "max_output_channels": 2,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.008,
        "default_high_input_latency": 0.1,
        "default_high_output_latency": 0.064,
        "default_samplerate": 8000.0,
    },
    {
        "name": "BlackHole 2ch",
        "index": 2,
        "hostapi": 0,
        "max_input_channels": 2,
        "max_output_channels": 2,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.0013333333333333333,
        "default_high_input_latency": 0.1,
        "default_high_output_latency": 0.010666666666666666,
        "default_samplerate": 48000.0,
    },
    {
        "name": "MacBook Pro Microphone",
        "index": 3,
        "hostapi": 0,
        "max_input_channels": 1,
        "max_output_channels": 0,
        "default_low_input_latency": 0.034520833333333334,
        "default_low_output_latency": 0.01,
        "default_high_input_latency": 0.043854166666666666,
        "default_high_output_latency": 0.1,
        "default_samplerate": 48000.0,
    },
    {
        "name": "MacBook Pro Speakers",
        "index": 4,
        "hostapi": 0,
        "max_input_channels": 0,
        "max_output_channels": 2,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.0070416666666666666,
        "default_high_input_latency": 0.1,
        "default_high_output_latency": 0.016375,
        "default_samplerate": 48000.0,
    },
    {
        "name": "Null Audio Device",
        "index": 5,
        "hostapi": 0,
        "max_input_channels": 2,
        "max_output_channels": 2,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.0014512471655328798,
        "default_high_input_latency": 0.1,
        "default_high_output_latency": 0.011609977324263039,
        "default_samplerate": 44100.0,
    },
    {
        "name": "Multi-Output Device",
        "index": 6,
        "hostapi": 0,
        "max_input_channels": 0,
        "max_output_channels": 2,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.0033333333333333335,
        "default_high_input_latency": 0.1,
        "default_high_output_latency": 0.012666666666666666,
        "default_samplerate": 48000.0,
    },
]


class MockInputStream:
    running = False
    thread: Thread

    def __init__(
        self,
        callback: Callable[[np.ndarray, int, Any, sounddevice.CallbackFlags], None],
        *args,
        **kwargs,
    ):
        self.thread = Thread(target=self.target)
        self.callback = callback

    def start(self):
        self.thread.start()

    def target(self):
        sample_rate = whisper_audio.SAMPLE_RATE
        file_path = os.path.join(
            os.path.dirname(__file__), "../testdata/whisper-french.mp3"
        )
        audio = whisper_audio.load_audio(file_path, sr=sample_rate)

        chunk_duration_secs = 1

        self.running = True
        seek = 0
        num_samples_in_chunk = chunk_duration_secs * sample_rate

        while self.running:
            time.sleep(chunk_duration_secs)
            chunk = audio[seek : seek + num_samples_in_chunk]
            self.callback(chunk, 0, None, sounddevice.CallbackFlags())
            seek += num_samples_in_chunk

            # loop back around
            if seek + num_samples_in_chunk > audio.size:
                seek = 0

    def stop(self):
        self.running = False
        self.thread.join()

    def close(self):
        self.stop()

    def __enter__(self):
        self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class MockSoundDevice:
    def __init__(self):
        self.devices = mock_query_devices

    def InputStream(self, *args, **kwargs):
        return MockInputStream(*args, **kwargs)

    def query_devices(self, device=None):
        if device is None:
            return self.devices
        else:
            return next((d for d in self.devices if d['index'] == device), None)

    def check_input_settings(self, device=None, samplerate=None):
        device_info = self.query_devices(device)
        if device_info and samplerate and samplerate != device_info['default_samplerate']:
            raise ValueError('Invalid sample rate for device')