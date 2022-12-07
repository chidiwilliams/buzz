import time
from contextlib import contextmanager
from threading import Thread
from unittest.mock import Mock, patch

import sounddevice
import whisper


def load_mock_input_stream(audio_path: str):
    class MockInputStream:
        """Mock implementation of sounddevice.InputStream
        """

        def __init__(self, blocksize: int, samplerate: int, callback, **args) -> None:
            self.callback = callback
            self.blocksize = blocksize
            self.samplerate = samplerate
            self.args = args

            self.audio = whisper.audio.load_audio(audio_path)
            self.thread = Thread(target=self.run_stream)
            self.stopped = False

        def start(self):
            self.thread.start()

        def run_stream(self):
            timeout = self.blocksize / self.samplerate

            current = 0
            while current < self.audio.size and self.stopped is False:
                time.sleep(timeout)

                next_chunk = Mock()
                next_chunk.ravel = Mock()
                next_chunk.ravel.return_value = self.audio[current:current+self.blocksize]

                self.callback(next_chunk, None, None, None)

                current = current + self.blocksize

        def close(self):
            self.stopped = True
            self.thread.join()

    return MockInputStream


@contextmanager
def sounddevice_mocks():
    with (patch('sounddevice.InputStream') as input_stream_mock,
            patch('sounddevice.query_devices') as query_devices_mock,
            patch('sounddevice.check_input_settings') as check_input_settings_mock):
        query_devices_mock.return_value = get_mock_audio_devices()
        sounddevice.default.device = 3, 4

        check_input_settings_mock.return_value = None

        input_stream_mock.side_effect = load_mock_input_stream(
            'testdata/whisper-french.mp3')

        yield


def get_mock_audio_devices():
    return [
        {'name': 'Background Music', 'index': 0, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
         'default_low_output_latency': 0.008, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.064, 'default_samplerate': 8000.0},
        {'name': 'Background Music (UI Sounds)', 'index': 1, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
                 'default_low_output_latency': 0.008, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.064, 'default_samplerate': 8000.0},
        {'name': 'BlackHole 2ch', 'index': 2, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
                 'default_low_output_latency': 0.0013333333333333333, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.010666666666666666, 'default_samplerate': 48000.0},
        {'name': 'MacBook Pro Microphone', 'index': 3, 'hostapi': 0, 'max_input_channels': 1, 'max_output_channels': 0, 'default_low_input_latency': 0.034520833333333334,
                 'default_low_output_latency': 0.01, 'default_high_input_latency': 0.043854166666666666, 'default_high_output_latency': 0.1, 'default_samplerate': 48000.0},
        {'name': 'MacBook Pro Speakers', 'index': 4, 'hostapi': 0, 'max_input_channels': 0, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
                 'default_low_output_latency': 0.0070416666666666666, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.016375, 'default_samplerate': 48000.0},
        {'name': 'Null Audio Device', 'index': 5, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
                 'default_low_output_latency': 0.0014512471655328798, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.011609977324263039, 'default_samplerate': 44100.0},
        {'name': 'Multi-Output Device', 'index': 6, 'hostapi': 0, 'max_input_channels': 0, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
                 'default_low_output_latency': 0.0033333333333333335, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.012666666666666666, 'default_samplerate': 48000.0},
    ]
