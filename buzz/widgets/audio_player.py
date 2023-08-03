from typing import Tuple, Optional

from PyQt6 import QtGui
from PyQt6.QtCore import QTime, QUrl, Qt
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import QWidget, QSlider, QPushButton, QLabel, QHBoxLayout

from buzz.locale import _


class AudioPlayer(QWidget):
    def __init__(self, file_path: str):
        super().__init__()

        self.range_ms: Optional[Tuple[int, int]] = None
        self.position = 0
        self.duration = 0

        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(100)

        self.media_player = QMediaPlayer()
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.media_player.setAudioOutput(self.audio_output)

        self.scrubber = QSlider(Qt.Orientation.Horizontal)
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderMoved.connect(self.on_slider_moved)

        self.play_button = QPushButton(_('Play'))
        self.play_button.clicked.connect(self.toggle_play)

        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout = QHBoxLayout()
        layout.addWidget(self.scrubber, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.time_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.play_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.setLayout(layout)

        # Connect media player signals to the corresponding slots
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.media_player.positionChanged.connect(self.on_position_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)

        self.update_time_label()

    def on_duration_changed(self, duration_ms: int):
        self.scrubber.setRange(0, duration_ms)
        self.duration = duration_ms
        self.update_time_label()

    def on_position_changed(self, position_ms: int):
        self.scrubber.setValue(position_ms)
        self.position = position_ms
        self.update_time_label()

        if self.range_ms is not None:
            start_range_ms, end_range_ms = self.range_ms
            if position_ms > end_range_ms:
                self.set_position(start_range_ms)

    def on_playback_state_changed(self, state: QMediaPlayer.PlaybackState):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setText(_('Pause'))
        else:
            self.play_button.setText(_('Play'))

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def set_range(self, range_ms: Tuple[int, int]):
        self.range_ms = range_ms
        self.set_position(range_ms[0])

    def on_slider_moved(self, position_ms: int):
        self.set_position(position_ms)
        # Reset range if slider is scrubbed manually
        self.range_ms = None

    def set_position(self, position_ms: int):
        self.media_player.setPosition(position_ms)

    def update_time_label(self):
        position_time = QTime(0, 0).addMSecs(self.position).toString()
        duration_time = QTime(0, 0).addMSecs(self.duration).toString()
        self.time_label.setText(f'{position_time} / {duration_time}')

    def stop(self):
        self.media_player.stop()

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        self.stop()
        super().closeEvent(a0)

    def hideEvent(self, a0: QtGui.QHideEvent) -> None:
        self.stop()
        super().hideEvent(a0)
