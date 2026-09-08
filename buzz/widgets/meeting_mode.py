"""Qt execution boundary for the authoritative meeting workflow."""

from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from buzz.meeting.meeting_audio_tracks import MeetingAudioTracksState
from buzz.meeting.meeting_workflow import MeetingWorkflowState


class _CaptureCall(QThread):
    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation
        self.error = None

    def run(self):
        try:
            self.operation()
        except Exception as exc:
            self.error = exc


class MeetingModeController(QObject):
    changed = pyqtSignal()
    saved = pyqtSignal(object)
    released = pyqtSignal()

    def __init__(self, workflow, parent=None):
        super().__init__(parent)
        self.workflow = workflow
        self.worker = None
        self.status = "Ready"
        self.error = ""
        self.saved_id = None
        self.duration_seconds = None
        self._end_requested = False
        self._poll = QTimer(self)
        self._poll.setInterval(250)
        self._poll.timeout.connect(self._observe)

    @property
    def active(self):
        return self.worker is not None or self.workflow.is_active

    def start(self, microphone, remote, kind):
        if self.active:
            raise RuntimeError("A meeting is already active or awaiting save/cleanup")
        self.saved_id = None
        self.duration_seconds = None
        self.error = ""
        self._end_requested = False
        self.status = "Starting…"
        self._run(lambda: self.workflow.start_capture(microphone, remote, kind))
        self._poll.start()

    def end(self):
        self._end_requested = True
        if self.worker is not None:
            return
        state = self.workflow.state
        if state is MeetingWorkflowState.ACTIVE:
            self.status = "Stopping and saving…"
            self._run(self.workflow.stop_capture)
        elif state is MeetingWorkflowState.CLEANUP_REQUIRED:
            self.status = "Retrying cleanup…"
            self._run(self.workflow.retry_cleanup)
        elif state is MeetingWorkflowState.AWAITING_PERSISTENCE:
            self._persist()

    def _run(self, operation):
        self.worker = _CaptureCall(operation, self)
        self.worker.finished.connect(self._finished)
        self.worker.start()
        self.changed.emit()

    @pyqtSlot()
    def _finished(self):
        worker = self.worker
        self.worker = None
        if worker.error is not None:
            self.error = str(worker.error)
        worker.deleteLater()
        state = self.workflow.state
        if state in (
            MeetingWorkflowState.AWAITING_PERSISTENCE,
            MeetingWorkflowState.CLEANUP_REQUIRED,
        ):
            self._persist()
        elif state is MeetingWorkflowState.ACTIVE:
            self.status = "Recording"
            if self._end_requested:
                self.end()
            else:
                self._observe()
        else:
            self.status = "Failed to start"
            self._poll.stop()
            if not self.active:
                self.released.emit()
        self.changed.emit()

    def _persist(self):
        # This object is created on the QSql owner thread. Worker completion
        # reaches this QObject slot through a queued Qt connection.
        assert QThread.currentThread() == self.thread()
        snapshot = self.workflow.snapshot()
        if snapshot.duration_ns is not None:
            self.duration_seconds = snapshot.duration_ns / 1e9
        try:
            result = self.workflow.persist()
        except Exception as exc:
            self.status = "Save failed — retry required"
            self.error = str(exc)
            self.changed.emit()
            return
        self.saved_id = result.session_id
        self._poll.stop()
        if self.workflow.is_active:
            self.status = "Recording preserved — cleanup still required"
        else:
            outcome = snapshot.audio.outcome.name if snapshot.audio else "FAILED"
            self.status = (
                "Meeting saved"
                if outcome == "COMPLETE"
                else "Meeting saved — partial audio"
                if outcome == "PARTIAL"
                else "Meeting saved — audio failed"
            )
        self.changed.emit()
        self.saved.emit(result)
        if not self.active:
            self.released.emit()

    def _observe(self):
        if self.workflow.state is MeetingWorkflowState.ACTIVE:
            snapshot = self.workflow.snapshot()
            self.status = (
                "Recording — degraded audio"
                if snapshot.audio_state is MeetingAudioTracksState.DEGRADED
                else "Recording"
            )
        self.changed.emit()
