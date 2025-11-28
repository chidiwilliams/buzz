from typing import Tuple, Optional
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTime
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSlider, QPushButton, QHBoxLayout, QLabel, QSizePolicy

class VideoPlayer(QWidget):
    position_ms_changed = pyqtSignal(int)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)

        self.range_ms: Optional[Tuple[int, int]] = None
        self.position_ms = 0
        self.duration_ms = 0
        self.is_looping = False
        self.is_slider_dragging = False

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(100)

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

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_playback)

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

    def toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.play_button.setText("Play")
        else:
            self.media_player.play()
            self.play_button.setText("Pause")

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

    def on_duration_changed(self, duration_ms: int):
        self.scrubber.setRange(0, duration_ms)
        self.duration_ms = duration_ms
        self.update_time_label()

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
