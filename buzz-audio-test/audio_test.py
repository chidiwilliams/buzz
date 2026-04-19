import os
import sys
import platform
import subprocess
import traceback

import numpy as np
import sounddevice
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices, QAudioDevice
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QGroupBox, QScrollArea, QSizePolicy
)


# When frozen by PyInstaller the sample is in sys._MEIPASS/samples/;
# during dev it lives in the repo at whisper.cpp/samples/.
def _find_sample() -> str:
    frozen_path = os.path.join(getattr(sys, "_MEIPASS", ""), "samples", "jfk.wav")
    if os.path.exists(frozen_path):
        return frozen_path
    return os.path.join(os.path.dirname(__file__), "..", "whisper.cpp", "samples", "jfk.wav")

SAMPLE_FILE = _find_sample()


def collect_system_info() -> str:
    lines = []
    lines.append(f"Platform: {platform.platform()}")
    lines.append(f"Python: {sys.version}")
    lines.append(f"Architecture: {platform.machine()}")

    try:
        import PyQt6.QtCore
        lines.append(f"PyQt6: {PyQt6.QtCore.PYQT_VERSION_STR}")
        lines.append(f"Qt: {PyQt6.QtCore.QT_VERSION_STR}")
    except Exception as e:
        lines.append(f"PyQt6 version error: {e}")

    try:
        import sounddevice as sd
        lines.append(f"sounddevice: {sd.__version__}")
        lines.append(f"PortAudio: {sd.get_portaudio_version()[1]}")
    except Exception as e:
        lines.append(f"sounddevice version error: {e}")

    return "\n".join(lines)


def collect_audio_devices() -> str:
    lines = []

    # --- sounddevice input devices ---
    lines.append("=== sounddevice Input Devices ===")
    try:
        devices = sounddevice.query_devices()
        default_in = sounddevice.default.device[0]
        default_out = sounddevice.default.device[1]
        lines.append(f"Default input device index:  {default_in}")
        lines.append(f"Default output device index: {default_out}")
        lines.append("")
        for d in devices:
            marker = ""
            if d["index"] == default_in:
                marker += " [DEFAULT IN]"
            if d["index"] == default_out:
                marker += " [DEFAULT OUT]"
            lines.append(
                f"  [{d['index']}] {d['name']}{marker}\n"
                f"       in={d['max_input_channels']} out={d['max_output_channels']} "
                f"sr={d['default_samplerate']:.0f} Hz  "
                f"hostapi={sounddevice.query_hostapis(d['hostapi'])['name']}"
            )
    except Exception as e:
        lines.append(f"ERROR querying sounddevice: {e}")
        lines.append(traceback.format_exc())

    lines.append("")

    # --- Qt audio output devices ---
    lines.append("=== Qt Audio Output Devices ===")
    try:
        qt_outputs = QMediaDevices.audioOutputs()
        default_qt_out = QMediaDevices.defaultAudioOutput()
        lines.append(f"Qt default output: {default_qt_out.description()}")
        lines.append(f"Total Qt output devices: {len(qt_outputs)}")
        for dev in qt_outputs:
            marker = " [DEFAULT]" if dev.id() == default_qt_out.id() else ""
            lines.append(f"  {dev.description()}{marker}  (id={dev.id().data().decode(errors='replace')[:40]})")
    except Exception as e:
        lines.append(f"ERROR querying Qt audio outputs: {e}")
        lines.append(traceback.format_exc())

    lines.append("")

    # --- Qt audio input devices ---
    lines.append("=== Qt Audio Input Devices ===")
    try:
        qt_inputs = QMediaDevices.audioInputs()
        default_qt_in = QMediaDevices.defaultAudioInput()
        lines.append(f"Qt default input: {default_qt_in.description()}")
        lines.append(f"Total Qt input devices: {len(qt_inputs)}")
        for dev in qt_inputs:
            marker = " [DEFAULT]" if dev.id() == default_qt_in.id() else ""
            lines.append(f"  {dev.description()}{marker}")
    except Exception as e:
        lines.append(f"ERROR querying Qt audio inputs: {e}")
        lines.append(traceback.format_exc())

    return "\n".join(lines)


class AudioTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Buzz Audio Diagnostics")
        self.resize(800, 700)

        self.audio_output = None
        self.media_player = None
        self.playback_log = []

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- System info ---
        sys_group = QGroupBox("System Information")
        sys_layout = QVBoxLayout(sys_group)
        self.sys_text = QTextEdit()
        self.sys_text.setReadOnly(True)
        self.sys_text.setMaximumHeight(120)
        self.sys_text.setPlainText(collect_system_info())
        sys_layout.addWidget(self.sys_text)
        layout.addWidget(sys_group)

        # --- Device info ---
        dev_group = QGroupBox("Audio Devices")
        dev_layout = QVBoxLayout(dev_group)
        self.dev_text = QTextEdit()
        self.dev_text.setReadOnly(True)
        self.dev_text.setMinimumHeight(200)
        dev_layout.addWidget(self.dev_text)
        refresh_btn = QPushButton("Refresh Device List")
        refresh_btn.clicked.connect(self.refresh_devices)
        dev_layout.addWidget(refresh_btn)
        layout.addWidget(dev_group)

        # --- Playback test ---
        play_group = QGroupBox("Playback Test  (jfk.wav)")
        play_layout = QVBoxLayout(play_group)

        btn_row = QHBoxLayout()
        self.play_btn = QPushButton("Play Audio")
        self.play_btn.clicked.connect(self.play_audio)
        btn_row.addWidget(self.play_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_audio)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.stop_btn)
        play_layout.addLayout(btn_row)

        self.status_label = QLabel("Status: idle")
        play_layout.addWidget(self.status_label)

        self.playback_log_text = QTextEdit()
        self.playback_log_text.setReadOnly(True)
        self.playback_log_text.setMaximumHeight(150)
        play_layout.addWidget(self.playback_log_text)
        layout.addWidget(play_group)

        # --- sounddevice playback test ---
        sd_group = QGroupBox("sounddevice Playback Test  (bypasses Qt multimedia)")
        sd_layout = QVBoxLayout(sd_group)
        sd_btn = QPushButton("Play via sounddevice")
        sd_btn.clicked.connect(self.play_sounddevice)
        sd_layout.addWidget(sd_btn)
        self.sd_log_text = QTextEdit()
        self.sd_log_text.setReadOnly(True)
        self.sd_log_text.setMaximumHeight(80)
        sd_layout.addWidget(self.sd_log_text)
        layout.addWidget(sd_group)

        # --- Copy all button ---
        copy_btn = QPushButton("Copy All Debug Info to Clipboard")
        copy_btn.clicked.connect(self.copy_all)
        layout.addWidget(copy_btn)

        self.refresh_devices()
        self._init_player()

    def _init_player(self):
        sample = os.path.abspath(SAMPLE_FILE)
        self._log(f"Sample file: {sample}")
        if not os.path.exists(sample):
            self._log("ERROR: Sample file not found!")
            self.play_btn.setEnabled(False)
            return

        try:
            self.audio_output = QAudioOutput()
            self.audio_output.setVolume(1.0)

            self.media_player = QMediaPlayer()
            self.media_player.setAudioOutput(self.audio_output)
            self.media_player.setSource(QUrl.fromLocalFile(sample))

            self.media_player.playbackStateChanged.connect(self._on_playback_state)
            self.media_player.mediaStatusChanged.connect(self._on_media_status)
            self.media_player.errorOccurred.connect(self._on_error)
            self.media_player.durationChanged.connect(self._on_duration_changed)

            default_out = QMediaDevices.defaultAudioOutput()
            self._log(f"QAudioOutput device: {self.audio_output.device().description()}")
            self._log(f"Qt default output:   {default_out.description()}")
        except Exception as e:
            self._log(f"ERROR initialising player: {e}")
            self._log(traceback.format_exc())

    def refresh_devices(self):
        self.dev_text.setPlainText(collect_audio_devices())

    def play_audio(self):
        if self.media_player is None:
            self._log("Player not initialised.")
            return
        self._log(f"QAudioOutput volume: {self.audio_output.volume()}")
        self._log(f"QAudioOutput muted:  {self.audio_output.isMuted()}")
        self._log(f"Media duration (ms): {self.media_player.duration()}")
        self._log(f"Media position (ms): {self.media_player.position()}")
        self._log("Calling media_player.play() …")
        self.media_player.play()
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_audio(self):
        if self.media_player:
            self.media_player.stop()
        self.play_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_playback_state(self, state: QMediaPlayer.PlaybackState):
        names = {
            QMediaPlayer.PlaybackState.StoppedState: "Stopped",
            QMediaPlayer.PlaybackState.PlayingState: "Playing",
            QMediaPlayer.PlaybackState.PausedState:  "Paused",
        }
        label = names.get(state, str(state))
        self._log(f"Playback state → {label}")
        self.status_label.setText(f"Status: {label}")
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.play_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def _on_media_status(self, status: QMediaPlayer.MediaStatus):
        names = {
            QMediaPlayer.MediaStatus.NoMedia:           "NoMedia",
            QMediaPlayer.MediaStatus.LoadingMedia:      "LoadingMedia",
            QMediaPlayer.MediaStatus.LoadedMedia:       "LoadedMedia",
            QMediaPlayer.MediaStatus.StalledMedia:      "StalledMedia",
            QMediaPlayer.MediaStatus.BufferingMedia:    "BufferingMedia",
            QMediaPlayer.MediaStatus.BufferedMedia:     "BufferedMedia",
            QMediaPlayer.MediaStatus.EndOfMedia:        "EndOfMedia",
            QMediaPlayer.MediaStatus.InvalidMedia:      "InvalidMedia",
        }
        self._log(f"Media status → {names.get(status, str(status))}")

    def _on_duration_changed(self, duration_ms: int):
        self._log(f"Duration changed → {duration_ms} ms")

    def _on_error(self, error: QMediaPlayer.Error, msg: str):
        self._log(f"ERROR {error}: {msg}")
        self.status_label.setText(f"Error: {msg}")

    def _log(self, msg: str):
        self.playback_log.append(msg)
        self.playback_log_text.append(msg)

    def play_sounddevice(self):
        import wave
        import numpy as np
        sample = os.path.abspath(SAMPLE_FILE)
        try:
            with wave.open(sample, "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)
            dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
            data = np.frombuffer(raw, dtype=dtype)
            if n_channels > 1:
                data = data.reshape(-1, n_channels)
            self.sd_log_text.append(f"WAV: {n_frames} frames, {framerate} Hz, {n_channels}ch")
            sounddevice.play(data.astype(np.float32) / np.iinfo(dtype).max, samplerate=framerate)
            self.sd_log_text.append("sounddevice.play() called — you should hear audio now")
        except Exception as e:
            self.sd_log_text.append(f"ERROR: {e}")
            self.sd_log_text.append(traceback.format_exc())

    def copy_all(self):
        text = "\n\n".join([
            "=== SYSTEM INFO ===",
            self.sys_text.toPlainText(),
            "=== AUDIO DEVICES ===",
            self.dev_text.toPlainText(),
            "=== PLAYBACK LOG ===",
            "\n".join(self.playback_log),
        ])
        QApplication.clipboard().setText(text)
        self.status_label.setText("Copied to clipboard!")


def main():
    app = QApplication(sys.argv)
    win = AudioTestWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
