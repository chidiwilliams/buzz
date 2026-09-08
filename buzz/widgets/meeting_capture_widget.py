"""Small meeting capture window; lifecycle belongs to MeetingWorkflow."""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from buzz.audio_capture.sounddevice_source import SoundDeviceAudioSource
from buzz.audio_capture.windows_application_targets import (
    list_windows_application_audio_targets,
    validate_windows_application_audio_target,
)
from buzz.audio_capture.windows_process_source import WindowsProcessAudioSource
from buzz.audio_capture.windows_system_source import WindowsSystemAudioSource
from buzz.meeting.final_transcription import FinalTranscriptionConfig
from buzz.meeting.meeting_session import MeetingRemoteSourceKind
from buzz.meeting.meeting_workflow import MeetingWorkflowState
from buzz.widgets.application_audio_target_combo_box import (
    ApplicationAudioTargetComboBox,
)
from buzz.widgets.audio_devices_combo_box import AudioDevicesComboBox


class MeetingCaptureWidget(QWidget):
    open_requested = pyqtSignal(object)

    def __init__(self, controller, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.controller = controller
        self.config = FinalTranscriptionConfig(whisper_model_size="SMALL")
        self._close_pending = False
        self._started_at = None
        self.setWindowTitle("New Meeting")
        self.microphone = AudioDevicesComboBox(self)
        self.remote = QComboBox(self)
        self.remote.addItem("System Audio", MeetingRemoteSourceKind.SYSTEM)
        self.remote.addItem("Application Audio", MeetingRemoteSourceKind.APPLICATION)
        self.target = ApplicationAudioTargetComboBox(self)
        self.refresh_targets = QPushButton("Refresh applications", self)
        self.model_size = QComboBox(self)
        self.model_size.addItems(["TINY", "BASE", "SMALL", "MEDIUM", "LARGEV3"])
        self.model_size.setCurrentText("SMALL")
        self.model_help = QLabel(
            "Final transcription uses a local Faster Whisper model. "
            "Download the selected model in Preferences → Models before transcription. "
            "If unavailable, your recording is saved and transcription can be retried.",
            self,
        )
        self.model_help.setWordWrap(True)
        self.start_button = QPushButton("Start", self)
        self.stop_button = QPushButton("Stop", self)
        self.open_button = QPushButton("Open Meeting Details", self)
        self.status_label = QLabel(self)
        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.elapsed_label = QLabel("00:00:00", self)
        layout = QFormLayout(self)
        layout.addRow("Microphone", self.microphone)
        layout.addRow("Meeting audio", self.remote)
        layout.addRow("Application", self.target)
        layout.addRow(self.refresh_targets)
        layout.addRow("Final transcription model", self.model_size)
        for widget in (
            self.model_help,
            self.start_button,
            self.stop_button,
            self.status_label,
            self.elapsed_label,
            self.error_label,
            self.open_button,
        ):
            layout.addRow(widget)
        self.start_button.clicked.connect(self._start)
        self.stop_button.clicked.connect(controller.end)
        self.open_button.clicked.connect(
            lambda: self.open_requested.emit(controller.saved_id)
        )
        self.refresh_targets.clicked.connect(self._refresh_targets)
        self.remote.currentIndexChanged.connect(self._source_changed)
        controller.changed.connect(self._render)
        controller.released.connect(self._released)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._render)
        self._timer.start()
        self._render()

    def _source_changed(self):
        if self.remote.currentData() is MeetingRemoteSourceKind.APPLICATION:
            self._refresh_targets()
        self._render()

    def _refresh_targets(self):
        try:
            self.target.set_targets(list_windows_application_audio_targets())
            self.controller.error = ""
        except Exception as exc:
            self.target.set_refresh_error()
            self.controller.error = str(exc)
        self._render()

    def _start(self):
        try:
            index = self.microphone.currentIndex()
            if index < 0:
                raise ValueError("Choose an available microphone")
            microphone = SoundDeviceAudioSource(
                self.microphone.audio_devices[index][0], 16000
            )
            kind = self.remote.currentData()
            if kind is MeetingRemoteSourceKind.SYSTEM:
                remote = WindowsSystemAudioSource()
            else:
                target = self.target.selected_target
                if target is None or not validate_windows_application_audio_target(
                    target
                ):
                    raise ValueError(
                        "Refresh applications and choose an available application"
                    )
                remote = WindowsProcessAudioSource(process_id=target.capture_pid)
            self.config = FinalTranscriptionConfig(
                whisper_model_size=self.model_size.currentText()
            )
            self._started_at = None
            self.controller.start(microphone, remote, kind)
        except Exception as exc:
            self.controller.error = str(exc)
            self._render()

    def _render(self):
        active = self.controller.active
        for widget in (self.microphone, self.remote, self.model_size):
            widget.setEnabled(not active)
        application = self.remote.currentData() is MeetingRemoteSourceKind.APPLICATION
        self.target.setEnabled(not active and application)
        self.refresh_targets.setEnabled(not active and application)
        self.start_button.setEnabled(not active)
        self.stop_button.setEnabled(active and self.controller.worker is None)
        self.stop_button.setText(
            {
                MeetingWorkflowState.AWAITING_PERSISTENCE: "Retry saving",
                MeetingWorkflowState.CLEANUP_REQUIRED: "Retry ending meeting",
            }.get(self.controller.workflow.state, "Stop")
        )
        self.open_button.setEnabled(self.controller.saved_id is not None)
        self.status_label.setText(self.controller.status)
        self.error_label.setText(self.controller.error)
        if self.controller.status.startswith("Recording") and self._started_at is None:
            self._started_at = time.monotonic()
        elapsed = None
        if self.controller.duration_seconds is not None:
            elapsed = int(self.controller.duration_seconds)
        elif active and self._started_at is not None:
            elapsed = int(time.monotonic() - self._started_at)
        if elapsed is not None:
            self.elapsed_label.setText(
                f"{elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}"
            )

    def confirm_end(self):
        return (
            QMessageBox.question(
                self,
                "End meeting?",
                "End and save this meeting before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _released(self):
        if self._close_pending:
            self._close_pending = False
            self.close()

    def closeEvent(self, event):
        if self.controller.active:
            event.ignore()
            if self.confirm_end():
                self._close_pending = True
                self.controller.end()
            else:
                self._close_pending = False
            return
        self._close_pending = False
        super().closeEvent(event)
