import logging
from typing import Tuple, Optional

import numpy as np
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTime, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QSlider, QPushButton,
    QHBoxLayout, QLabel, QSizePolicy,
)
from buzz.widgets.icon import PlayIcon, PauseIcon
from buzz.sounddevice_player import AudioFilePlayer
from buzz.ffmpeg_video_player import FfmpegVideoPlayer


class VideoPlayer(QWidget):
    position_ms_changed = pyqtSignal(int)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)

        self.range_ms: Optional[Tuple[int, int]] = None
        self.position_ms = 0
        self.duration_ms = 0
        self.is_looping = False
        self.is_slider_dragging = False

        # --- ffmpeg software video decoder (avoids Qt GPU renderer artefacts) ---
        self._ffmpeg_player = FfmpegVideoPlayer(file_path)
        if self._ffmpeg_player.has_video:
            self._ffmpeg_player.start(0)

        # --- sounddevice audio engine ---
        self._sd_player: Optional[AudioFilePlayer] = None
        self._use_sd = False
        try:
            sd_player = AudioFilePlayer(file_path)
            if sd_player.ready:
                self._sd_player = sd_player
                self._use_sd = True
            else:
                sd_player.close()
        except Exception:
            logging.warning("VideoPlayer: sounddevice init failed, no audio", exc_info=True)

        # --- Qt multimedia: position/duration clock only (muted, no video output) ---
        self.audio_output = QAudioOutput(self)
        self.audio_output.setMuted(True)
        self.media_player = QMediaPlayer(self)
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.media_player.setAudioOutput(self.audio_output)
        # No setVideoOutput — we render frames ourselves via ffmpeg

        # Seed duration from ffprobe immediately so the scrubber is usable
        # before QMediaPlayer's async durationChanged fires.
        if self._ffmpeg_player.duration_ms > 0:
            self.duration_ms = self._ffmpeg_player.duration_ms
            self.scrubber_initial_max = self._ffmpeg_player.duration_ms
        else:
            self.scrubber_initial_max = 0

        # --- Video display label ---
        self.video_label = QLabel(self)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumHeight(200)
        self.video_label.setMaximumHeight(400)
        self.video_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )
        self.video_label.setStyleSheet("background-color: black;")

        # Render timer — fires at video fps, updates the label with the current frame
        render_interval_ms = max(16, int(1000 / self._ffmpeg_player.fps))
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(render_interval_ms)
        self._render_timer.timeout.connect(self._render_frame)
        self._render_timer.start()

        # Audio sync timer — keeps sounddevice within 200 ms of QMediaPlayer position
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._sync_audio)

        # --- Controls ---
        self.scrubber = QSlider(Qt.Orientation.Horizontal)
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderMoved.connect(self.on_slider_moved)
        self.scrubber.sliderPressed.connect(self.on_slider_pressed)
        self.scrubber.sliderReleased.connect(self.on_slider_released)

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
        layout.addWidget(self.video_label, stretch=1)
        layout.addLayout(controls)
        self.setLayout(layout)

        self.media_player.positionChanged.connect(self.on_position_changed)
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.media_player.errorOccurred.connect(self.on_error_occurred)

        if self.scrubber_initial_max > 0:
            self.scrubber.setRange(0, self.scrubber_initial_max)
            self.update_time_label()

    # ------------------------------------------------------------------
    # Frame rendering
    # ------------------------------------------------------------------

    def _render_frame(self):
        frame = self._ffmpeg_player.get_frame_for_position(self.position_ms)
        if frame is None:
            frame = self._ffmpeg_player.last_frame
        if frame is not None:
            self._display_frame(frame)

    def _display_frame(self, frame: np.ndarray):
        h, w, _ = frame.shape
        img = QImage(frame.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(img)
        scaled = pixmap.scaled(
            self.video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.video_label.setPixmap(scaled)

    # ------------------------------------------------------------------
    # Audio sync
    # ------------------------------------------------------------------

    def _sync_audio(self):
        if self._sd_player is None:
            return
        video_pos = self.media_player.position()
        audio_pos = self._sd_player.position_ms
        if abs(video_pos - audio_pos) > 200:
            self._sd_player.seek(video_pos)

    # ------------------------------------------------------------------
    # Qt multimedia callbacks
    # ------------------------------------------------------------------

    def on_error_occurred(self, error: QMediaPlayer.Error, error_string: str):
        logging.error(f"Media player error: {error} - {error_string}")

    def on_media_status_changed(self, status: QMediaPlayer.MediaStatus):
        pass  # duration comes from ffprobe (immediate) or durationChanged (async)

    def toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            if self._use_sd and self._sd_player:
                self._sd_player.pause()
                self._poll_timer.stop()
        else:
            self.media_player.play()
            if self._use_sd and self._sd_player:
                self._sd_player.seek(self.media_player.position())
                self._sd_player.resume()
                self._poll_timer.start()

    def on_slider_moved(self, position):
        self.set_position(position)

    def on_slider_pressed(self):
        self.is_slider_dragging = True

    def on_slider_released(self):
        self.is_slider_dragging = False
        self.set_position(self.scrubber.value())

    def set_position(self, position_ms: int):
        self.media_player.setPosition(position_ms)
        self._ffmpeg_player.seek(position_ms)
        if self._use_sd and self._sd_player:
            self._sd_player.seek(position_ms)

    def on_position_changed(self, position_ms: int):
        if not self.is_slider_dragging:
            self.scrubber.blockSignals(True)
            self.scrubber.setValue(position_ms)
            self.scrubber.blockSignals(False)

        self.position_ms = position_ms
        self.position_ms_changed.emit(position_ms)
        self.update_time_label()

        if self.range_ms is not None and not self.is_looping:
            start_range_ms, end_range_ms = self.range_ms
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
        self.range_ms = range_ms
        start_range_ms, end_range_ms = range_ms
        if self.position_ms < start_range_ms or self.position_ms > end_range_ms:
            self.set_position(start_range_ms)

    def clear_range(self):
        self.range_ms = None

    def stop(self):
        self.media_player.stop()
        self._render_timer.stop()
        if self._use_sd and self._sd_player:
            self._poll_timer.stop()
            self._sd_player.stop()

    def closeEvent(self, event):
        self.stop()
        self._ffmpeg_player.close()
        if self._sd_player:
            self._sd_player.close()
        super().closeEvent(event)
