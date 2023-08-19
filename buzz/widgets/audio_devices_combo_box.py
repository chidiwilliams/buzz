from typing import List, Tuple, Optional

import sounddevice
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QWidget, QMessageBox


class AudioDevicesComboBox(QComboBox):
    """AudioDevicesComboBox displays a list of available audio input devices"""

    device_changed = pyqtSignal(int)
    audio_devices: List[Tuple[int, str]]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.audio_devices = self.get_audio_devices()
        self.addItems([device[1] for device in self.audio_devices])
        self.currentIndexChanged.connect(self.on_index_changed)

        default_device_id = self.get_default_device_id()
        if default_device_id != -1:
            for i, device in enumerate(self.audio_devices):
                if device[0] == default_device_id:
                    self.setCurrentIndex(i)

    def get_audio_devices(self) -> List[Tuple[int, str]]:
        try:
            devices: sounddevice.DeviceList = sounddevice.query_devices()
            return [
                (device.get("index"), device.get("name"))
                for device in devices
                if device.get("max_input_channels") > 0
            ]
        except UnicodeDecodeError:
            QMessageBox.critical(
                self,
                "",
                "An error occurred while loading your audio devices. Please check the application logs for more "
                "information.",
            )
            return []

    def on_index_changed(self, index: int):
        self.device_changed.emit(self.audio_devices[index][0])

    def get_default_device_id(self) -> Optional[int]:
        default_system_device = sounddevice.default.device[0]
        if default_system_device != -1:
            return default_system_device

        audio_devices = self.get_audio_devices()
        if len(audio_devices) > 0:
            return audio_devices[0][0]

        return -1
