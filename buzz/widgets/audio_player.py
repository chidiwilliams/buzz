import logging
from typing import Tuple, Optional

from PyQt6 import QtGui
from PyQt6.QtCore import QTime, QUrl, Qt, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import QWidget, QSlider, QPushButton, QLabel, QHBoxLayout, QVBoxLayout, QComboBox

from buzz.widgets.icon import PlayIcon, PauseIcon
from buzz.settings.settings import Settings


class AudioPlayer(QWidget):
    position_ms_changed = pyqtSignal(int)

    def __init__(self, file_path: str):
        super().__init__()

        self.range_ms: Optional[Tuple[int, int]] = None
        self.position_ms = 0
        self.duration_ms = 0
        self.invalid_media = None
        self.is_looping = False  # Flag to prevent recursive position changes

        # Initialize settings
        self.settings = Settings()

        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(100)

        self.media_player = QMediaPlayer()
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.media_player.setAudioOutput(self.audio_output)

        # Speed control moved to transcription viewer - just set default rate
        saved_rate = self.settings.value(Settings.Key.AUDIO_PLAYBACK_RATE, 1.0, float)
        saved_rate = max(0.1, min(5.0, saved_rate))  # Ensure valid range
        self.media_player.setPlaybackRate(saved_rate)

        self.scrubber = QSlider(Qt.Orientation.Horizontal)
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderMoved.connect(self.on_slider_moved)

        self.play_icon = PlayIcon(self)
        self.pause_icon = PauseIcon(self)

        self.play_button = QPushButton("")
        self.play_button.setIcon(self.play_icon)
        self.play_button.clicked.connect(self.toggle_play)

        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        # Create main layout - simplified without speed controls
        main_layout = QHBoxLayout()
        main_layout.addWidget(self.play_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        main_layout.addWidget(self.scrubber, alignment=Qt.AlignmentFlag.AlignVCenter)
        main_layout.addWidget(self.time_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.setLayout(main_layout)

        # Connect media player signals to the corresponding slots
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.media_player.positionChanged.connect(self.on_position_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)

        self.on_duration_changed(self.media_player.duration())

    def on_duration_changed(self, duration_ms: int):
        self.scrubber.setRange(0, duration_ms)
        self.duration_ms = duration_ms
        self.update_time_label()

    def on_position_changed(self, position_ms: int):
        self.scrubber.setValue(position_ms)
        self.position_ms = position_ms
        self.position_ms_changed.emit(self.position_ms)
        self.update_time_label()

        # If a range has been selected as we've reached the end of the range,
        # loop back to the start of the range
        if self.range_ms is not None and not self.is_looping:
            start_range_ms, end_range_ms = self.range_ms
            # Check if we're at or past the end of the range (with small buffer for precision)
            if position_ms >= (end_range_ms - 50):  # Within 50ms of end
                logging.debug(f"🔄 LOOP: Reached end {end_range_ms}ms, jumping to start {start_range_ms}ms")
                self.is_looping = True  # Set flag to prevent recursion
                self.set_position(start_range_ms)
                # Reset flag immediately after setting position
                self.is_looping = False

    def on_playback_state_changed(self, state: QMediaPlayer.PlaybackState):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setIcon(self.pause_icon)
        else:
            self.play_button.setIcon(self.play_icon)

    def on_media_status_changed(self, status: QMediaPlayer.MediaStatus):
        match status:
            case QMediaPlayer.MediaStatus.InvalidMedia:
                self.set_invalid_media(True)
            case QMediaPlayer.MediaStatus.LoadedMedia:
                self.set_invalid_media(False)

    def set_invalid_media(self, invalid_media: bool):
        self.invalid_media = invalid_media
        if self.invalid_media:
            self.play_button.setDisabled(True)
            self.scrubber.setRange(0, 1)
            self.scrubber.setDisabled(True)
            self.time_label.setDisabled(True)
        else:
            self.play_button.setEnabled(True)
            self.scrubber.setEnabled(True)
            self.time_label.setEnabled(True)

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def set_range(self, range_ms: Tuple[int, int]):
        """Set a loop range. Only jump to start if current position is outside the range."""
        self.range_ms = range_ms
        start_range_ms, end_range_ms = range_ms
        
        # Only jump to start if current position is outside the range
        if self.position_ms < start_range_ms or self.position_ms > end_range_ms:
            logging.debug(f"🔄 LOOP: Position {self.position_ms}ms outside range, jumping to {start_range_ms}ms")
            self.set_position(start_range_ms)

    def clear_range(self):
        """Clear the current loop range"""
        self.range_ms = None

    def _reset_looping_flag(self):
        """Reset the looping flag"""
        self.is_looping = False

    def on_slider_moved(self, position_ms: int):
        self.set_position(position_ms)
        # Only clear range if scrubbed significantly outside the current range
        if self.range_ms is not None:
            start_range_ms, end_range_ms = self.range_ms
            # Clear range if scrubbed more than 2 seconds outside the range
            if position_ms < (start_range_ms - 2000) or position_ms > (end_range_ms + 2000):
                self.range_ms = None

    def set_position(self, position_ms: int):
        self.media_player.setPosition(position_ms)

    def update_time_label(self):
        position_time = QTime(0, 0).addMSecs(self.position_ms).toString()
        duration_time = QTime(0, 0).addMSecs(self.duration_ms).toString()
        self.time_label.setText(f"{position_time} / {duration_time}")

    def stop(self):
        self.media_player.stop()

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        self.stop()
        super().closeEvent(a0)

    def hideEvent(self, a0: QtGui.QHideEvent) -> None:
        self.stop()
        super().hideEvent(a0)
