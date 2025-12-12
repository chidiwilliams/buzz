import logging
from typing import Tuple, Optional
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTime
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSlider, QPushButton, QHBoxLayout, QLabel, QSizePolicy
from buzz.widgets.icon import PlayIcon, PauseIcon

class VideoPlayer(QWidget):
    position_ms_changed = pyqtSignal(int)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)

        self.range_ms: Optional[Tuple[int, int]] = None
        self.position_ms = 0
        self.duration_ms = 0
        self.is_looping = False
        self.is_slider_dragging = False
        self.initial_frame_loaded = False

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(100)

        # Log audio device info for debugging
        default_device = QMediaDevices.defaultAudioOutput()
        if default_device.isNull():
            logging.warning("No default audio output device found!")
        else:
            logging.info(f"Audio output device: {default_device.description()}")

        self.media_player = QMediaPlayer(self)
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.media_player.setAudioOutput(self.audio_output)

        self.video_widget = QVideoWidget(self)
        self.media_player.setVideoOutput(self.video_widget)

        # Size constraints for video widget
        self.video_widget.setMinimumHeight(200)
        self.video_widget.setMaximumHeight(400)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.scrubber = QSlider(Qt.Orientation.Horizontal)
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderMoved.connect(self.on_slider_moved)
        self.scrubber.sliderPressed.connect(self.on_slider_pressed)
        self.scrubber.sliderReleased.connect(self.on_slider_released)

        #Track if user is dragging the slider
        self.is_slider_dragging = False

        self.play_icon = PlayIcon(self)
        self.pause_icon = PauseIcon(self)

        self.play_button = QPushButton("")
        self.play_button.setIcon(self.play_icon)
        self.play_button.clicked.connect(self.toggle_playback)
        self.play_button.setMaximumWidth(40)
        self.play_button.setMinimumHeight(30)

        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.scrubber)
        controls.addWidget(self.time_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.video_widget, stretch=1)
        layout.addLayout(controls)

        self.setLayout(layout)


        self.media_player.positionChanged.connect(self.on_position_changed)
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.media_player.errorOccurred.connect(self.on_error_occurred)

    def on_error_occurred(self, error: QMediaPlayer.Error, error_string: str):
        logging.error(f"Media player error: {error} - {error_string}")

    def on_media_status_changed(self, status: QMediaPlayer.MediaStatus):
        # Only do this once on initial load to show first frame
        if self.initial_frame_loaded:
            return
        # Start playback when loaded to trigger frame decoding
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self.media_player.play()
        # Pause immediately when buffered to show first frame
        elif status == QMediaPlayer.MediaStatus.BufferedMedia:
            self.initial_frame_loaded = True
            self.media_player.pause()

    def toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def on_slider_moved(self, position):
        self.set_position(position)

    def on_slider_pressed(self):
        """Called when user starts dragging the slider"""
        self.is_slider_dragging = True

    def on_slider_released(self):
        """Called when user releases the slider"""
        self.is_slider_dragging = False
        # Update position to where use released
        self.set_position(self.scrubber.value())

    def set_position(self, position_ms: int):
        self.media_player.setPosition(position_ms)

    def on_position_changed(self, position_ms: int):
        # Don't update slider if user is currently dragging it
        if not self.is_slider_dragging:
            self.scrubber.blockSignals(True)
            self.scrubber.setValue(position_ms)
            self.scrubber.blockSignals(False)

        self.position_ms = position_ms
        self.position_ms_changed.emit(position_ms)
        self.update_time_label()

        # If a range has been selected and video has reached the end of range
        #loop back to the start of the range
        if self.range_ms is not None and not self.is_looping:
            start_range_ms, end_range_ms = self.range_ms
            #Check if video is at or past the end of range
            if position_ms >= (end_range_ms - 50):
                self.is_looping = True
                self.set_position(start_range_ms)
                self.is_looping = False

    def on_duration_changed(self, duration_ms: int):
        self.scrubber.setRange(0, duration_ms)
        self.duration_ms = duration_ms
        self.update_time_label()

    def on_playback_state_changed(self, state: QMediaPlayer.PlaybackState):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setIcon(self.pause_icon)
        else:
            self.play_button.setIcon(self.play_icon)

    def update_time_label(self):
        position_time = QTime(0, 0).addMSecs(self.position_ms).toString()
        duration_time = QTime(0, 0).addMSecs(self.duration_ms).toString()
        self.time_label.setText(f"{position_time} / {duration_time}")

    def set_range(self, range_ms: Tuple[int, int]):
        """Set a loop range. Only jump to start if current position is outside the range."""
        self.range_ms = range_ms
        start_range_ms, end_range_ms = range_ms

        if self.position_ms < start_range_ms or self.position_ms > end_range_ms:
            self.set_position(start_range_ms)

    def clear_range(self):
        """Clear the current loop range"""
        self.range_ms = None

    def stop(self):
        self.media_player.stop()
