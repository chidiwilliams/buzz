from typing import Optional

import logging
import numpy as np
import sounddevice
from PyQt6.QtCore import QObject, pyqtSignal


class RecordingAmplitudeListener(QObject):
    stream: Optional[sounddevice.InputStream] = None
    amplitude_changed = pyqtSignal(float)
    average_amplitude_changed = pyqtSignal(float)

    ACCUMULATION_SECONDS = 1

    def __init__(
        self,
        input_device_index: Optional[int] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.input_device_index = input_device_index
        self.buffer = np.ndarray([], dtype=np.float32)
        self.accumulation_size = 0

    def start_recording(self):
        try:
            self.stream = sounddevice.InputStream(
                device=self.input_device_index,
                dtype="float32",
                channels=1,
                callback=self.stream_callback,
            )
            self.stream.start()
            self.accumulation_size = int(self.stream.samplerate * self.ACCUMULATION_SECONDS)
        except Exception as e:
            self.stop_recording()
            logging.exception("Failed to start audio stream on device %s: %s", self.input_device_index, e)

    def stop_recording(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()

    def stream_callback(self, in_data: np.ndarray, frame_count, time_info, status):
        chunk = in_data.ravel()
        self.amplitude_changed.emit(float(np.sqrt(np.mean(chunk**2))))

        self.buffer = np.append(self.buffer, chunk)
        if self.buffer.size >= self.accumulation_size:
            self.average_amplitude_changed.emit(float(np.sqrt(np.mean(self.buffer**2))))
            self.buffer = np.ndarray([], dtype=np.float32)
