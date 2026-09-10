"""Application-lifetime Qt execution and ownership for AI Notes."""
from __future__ import annotations

import uuid
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from buzz.meeting.meeting_notes import NotesError, SourceChangedError
from buzz.meeting.openai_compatible_provider import OpenAICompatibleProvider
from buzz.meeting.portable_ai_request import render_portable_ai_meeting_request
from buzz.meeting.summary_provider import validate_summary_provider_result
from buzz.meeting.meeting_summary_provenance import (
    validate_meeting_summary_timestamp_provenance,
)


class NotesWorker(QObject):
    outcome = pyqtSignal(object, object, object, str)
    cleaned = pyqtSignal()

    def __init__(self, operation_id, context, config, factory):
        super().__init__()
        self.operation_id = operation_id
        self.context = context
        self.config = config
        self.factory = factory
        self.provider = None

    @pyqtSlot()
    def run(self):
        result, error = None, ""
        try:
            self.provider = self.factory(self.config)
            result = self.provider.summarize(self.context.request)
            validate_summary_provider_result(self.context.request, result)
            validate_meeting_summary_timestamp_provenance(self.context.request, result)
        except Exception:
            # Never forward exceptions, headers, raw response, or configuration.
            error = "API generation failed. Check configuration and retry explicitly."
            result = None
        self.outcome.emit(self.operation_id, self.context, result, error)
        # Owner-thread result handling acknowledges before cleanup can begin.

    @pyqtSlot()
    def cleanup(self):
        try:
            complete = self.provider is None or (
                self.provider.shutdown() is True and not self.provider.cleanup_required
            )
        except Exception:
            complete = False
        if not complete:
            QTimer.singleShot(250, self.cleanup)
            return
        self.cleaned.emit()


class MeetingNotesController(QObject):
    changed = pyqtSignal(object, object)  # originating meeting, newly saved ID or None
    status = pyqtSignal(object, str)
    idle = pyqtSignal()
    cleanup_requested = pyqtSignal()

    def __init__(self, service, parent=None, provider_factory=OpenAICompatibleProvider):
        super().__init__(parent)
        self.service = service
        self.provider_factory = provider_factory
        self.closing = False
        self.worker = None
        self.worker_thread = None
        self.operation_id = None
        self.operation_meeting_id = None
        self._delivered = False
        self.manual_contexts = {}
        self.candidates = {}

    def _owner(self):
        if QThread.currentThread() != self.thread():
            raise RuntimeError("AI Notes controller requires its owner thread")

    @property
    def busy(self):
        return self.operation_id is not None

    def copy_request(self, meeting_id, copy=None):
        self._owner()
        context = self.service.prepare(meeting_id)
        rendered = render_portable_ai_meeting_request(context.request)
        if copy is not None:
            copy(rendered)
        self.manual_contexts[meeting_id] = context
        return rendered

    def import_response(self, meeting_id, text, *, repair=False):
        self._owner()
        context = self.manual_contexts.get(meeting_id)
        summary = self.service.import_response(context, text, repair=repair)
        return self._save_result(context, summary)

    def _save_result(self, context, summary):
        self._owner()
        # Do not discard a candidate awaiting an intentional save retry.
        if context.meeting_id in self.candidates:
            raise NotesError(
                "Retry or discard the pending save before creating another summary."
            )
        candidate = self.service.candidate(context, summary)
        self.candidates[context.meeting_id] = candidate
        return self.retry_save(context.meeting_id)

    def retry_save(self, meeting_id):
        self._owner()
        candidate = self.candidates[meeting_id]
        try:
            artifact = self.service.save(candidate)
        except SourceChangedError:
            del self.candidates[meeting_id]
            raise
        del self.candidates[meeting_id]
        self.changed.emit(meeting_id, artifact.summary_id)
        if self.closing and not self.busy:
            self.idle.emit()
        return artifact

    def discard_save(self, meeting_id):
        self._owner()
        self.candidates.pop(meeting_id, None)
        self.changed.emit(meeting_id, None)
        if self.closing and not self.busy:
            self.idle.emit()

    def submit(self, meeting_id, config):
        self._owner()
        if self.closing or self.busy:
            raise NotesError("API generation is busy or the application is closing.")
        if meeting_id in self.candidates:
            raise NotesError("Retry or discard the pending save first.")
        context = self.service.prepare(meeting_id)
        self.operation_id = uuid.uuid4()
        self.operation_meeting_id = meeting_id
        self._delivered = False
        self.worker_thread = QThread(self)
        self.worker = NotesWorker(
            self.operation_id, context, config, self.provider_factory
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.outcome.connect(self._outcome)
        self.cleanup_requested.connect(self.worker.cleanup)
        self.worker.cleaned.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self._finished)
        self.worker_thread.start()
        self.status.emit(meeting_id, "Generating AI Notes…")
        self.changed.emit(meeting_id, None)

    @pyqtSlot(object, object, object, str)
    def _outcome(self, operation_id, context, summary, error):
        self._owner()
        if (
            operation_id != self.operation_id
            or context.meeting_id != self.operation_meeting_id
        ):
            return
        try:
            if error:
                self.status.emit(context.meeting_id, error)
            else:
                self._save_result(context, summary)
                self.status.emit(context.meeting_id, "AI Notes saved.")
        except SourceChangedError:
            self.status.emit(
                context.meeting_id,
                "Source changed or cannot be verified. Result was not saved.",
            )
        except Exception:
            message = (
                "Save failed. Retry Save retains the same summary."
                if context.meeting_id in self.candidates
                else "API result failed validation. Nothing was saved."
            )
            self.status.emit(context.meeting_id, message)
        finally:
            self._delivered = True
            self.changed.emit(context.meeting_id, None)
            self.cleanup_requested.emit()

    @pyqtSlot()
    def _finished(self):
        self._owner()
        if self.worker_thread is None:
            return
        if not self._delivered or not self.worker_thread.wait(0):
            QTimer.singleShot(10, self._finished)
            return
        meeting_id = self.operation_meeting_id
        self.worker = None
        self.worker_thread.deleteLater()
        self.worker_thread = None
        self.operation_id = self.operation_meeting_id = None
        self.changed.emit(meeting_id, None)
        self.idle.emit()

    def close(self):
        self._owner()
        self.closing = True
        return not self.busy and not self.candidates

    def prepare(self, meeting_id):
        self._owner()
        return self.service.prepare(meeting_id)

    def history(self, meeting_id):
        self._owner()
        return self.service.history(meeting_id)

    def freshness(self, artifact):
        self._owner()
        return self.service.freshness(artifact)

    def selected(self, meeting_id, summary_id):
        self._owner()
        return self.service.selected(meeting_id, summary_id)

    def export(self, meeting_id, summary_id, path, *, acknowledged=False):
        self._owner()
        return self.service.export(
            meeting_id, summary_id, path, acknowledged=acknowledged
        )
