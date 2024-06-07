from typing import Optional

import logging
import numpy as np
import sounddevice
from PyQt6.QtCore import QObject, pyqtSignal


class RecordingAmplitudeListener(QObject):
    stream: Optional[sounddevice.InputStream] = None
    amplitude_changed = pyqtSignal(float)

    def __init__(
        self,
        input_device_index: Optional[int] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.input_device_index = input_device_index

    def start_recording(self):
        try:
            self.stream = sounddevice.InputStream(
                device=self.input_device_index,
                dtype="float32",
                channels=1,
                callback=self.stream_callback,
            )
            self.stream.start()
        except sounddevice.PortAudioError:
            self.stop_recording()
            logging.exception("")

    def stop_recording(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()

    def stream_callback(self, in_data: np.ndarray, frame_count, time_info, status):
        chunk = in_data.ravel()
        amplitude = np.sqrt(np.mean(chunk**2))  # root-mean-square
        self.amplitude_changed.emit(amplitude)
