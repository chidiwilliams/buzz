"""Run the existing synchronous service without moving QSql across threads.

The service owns scheduling and retry semantics. These Qt bridges only dispatch
its calls: repository operations to their owner, and ASR to the existing adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event

from PyQt6.QtCore import QEventLoop, QObject, QThread, pyqtSignal, pyqtSlot

from buzz.meeting.final_transcription import FinalTranscriptionService


class _ResultReady(QObject):
    ready = pyqtSignal()


@dataclass
class _Call:
    target: object
    name: str
    args: tuple
    kwargs: dict
    done: Event = field(default_factory=Event)
    result: object = None
    error: Exception | None = None
    notification: _ResultReady | None = None

    def finish(self):
        self.done.set()
        if self.notification is not None:
            self.notification.ready.emit()

    def wait(self):
        self.done.wait()
        if self.error is not None:
            raise self.error
        return self.result


class _OwnerProxy:
    def __init__(self, bridge, target):
        self.bridge = bridge
        self.target = target

    def __getattr__(self, name):
        def invoke(*args, **kwargs):
            call = _Call(self.target, name, args, kwargs)
            self.bridge.dispatch.emit(call)
            return call.wait()

        return invoke


class _Runner:
    def __init__(self, bridge):
        self.bridge = bridge

    def transcribe_track(self, audio_path, sample_rate, config, on_progress=None):
        call = _Call(None, "transcribe", (audio_path, sample_rate, config), {})
        loop = QEventLoop()
        call.notification = _ResultReady()
        call.notification.ready.connect(loop.quit)
        self.bridge.transcribe.emit(call)
        # Dispatch new request/retry commands on this same service thread only
        # while ASR is outstanding. The existing service's active-track guard
        # queues those tracks, making their durable QUEUED status visible now.
        # Repository calls still wait without pumping events, so transactions
        # and other service mutations are never re-entered.
        if not call.done.is_set():
            loop.exec()
        return call.wait()

    def shutdown(self):
        pass  # Owner only shuts down after all service calls have returned.


class _ServiceWorker(QObject):
    finished = pyqtSignal(object)

    def __init__(self, service):
        super().__init__()
        self.service = service

    @pyqtSlot(object)
    def execute(self, command):
        name, args = command
        error = None
        try:
            getattr(self.service, name)(*args)
        except Exception as exc:
            error = exc
        self.finished.emit(error)


class MeetingFinalTranscription(QObject):
    dispatch = pyqtSignal(object)
    transcribe = pyqtSignal(object)
    execute = pyqtSignal(object)
    changed = pyqtSignal()
    idle = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, storage, repository, adapter, parent=None):
        super().__init__(parent)
        self.adapter = adapter
        adapter.setParent(self)
        self.pending = 0
        self._asr_call = None
        self._closed = False
        self.dispatch.connect(self._dispatch)
        self.transcribe.connect(self._transcribe)
        adapter.track_completed.connect(self._segments)
        adapter.track_rich_completed.connect(self._complete)
        adapter.track_error.connect(self._error)
        self._service = FinalTranscriptionService(
            _OwnerProxy(self, storage), _OwnerProxy(self, repository), _Runner(self)
        )
        self._thread = QThread(self)
        self._worker = None

    def request(self, meeting_id, config):
        self._submit("request", meeting_id, config)

    def retry(self, generation_id):
        self._submit("retry", generation_id)

    def recover(self):
        self._submit("recover_pending")

    def _submit(self, name, *args):
        if self._closed:
            raise RuntimeError("Final transcription is closed")
        if not self.pending:
            self._worker = _ServiceWorker(self._service)
            self._worker.moveToThread(self._thread)
            self.execute.connect(self._worker.execute)
            self._worker.finished.connect(self._finished)
            self._thread.finished.connect(self._worker.deleteLater)
            self._thread.start()
        self.pending += 1
        self.execute.emit((name, args))
        self.changed.emit()

    @pyqtSlot(object)
    def _dispatch(self, call):
        assert QThread.currentThread() == self.thread()
        try:
            call.result = getattr(call.target, call.name)(*call.args, **call.kwargs)
        except Exception as exc:
            call.error = exc
        finally:
            call.finish()
        if call.name in {
            "create_generation",
            "begin_track",
            "complete_track",
            "fail_track",
            "mark_track_ineligible",
            "update_generation_status",
            "reset_for_retry",
            "reset_in_progress_tracks",
        }:
            self.changed.emit()

    @pyqtSlot(object)
    def _transcribe(self, call):
        if self._closed:
            call.error = RuntimeError("Final transcription is shutting down")
            call.finish()
            return
        self._asr_call = call
        try:
            self.adapter.start(*call.args)
        except Exception as exc:
            self._error(str(exc))

    def _segments(self, segments):
        self._complete(tuple(segments))

    def _complete(self, result):
        if self._closed:
            return
        call, self._asr_call = self._asr_call, None
        if call is not None:
            call.result = result
            call.finish()

    def _error(self, message):
        if self._closed:
            return
        call, self._asr_call = self._asr_call, None
        if call is not None:
            call.error = RuntimeError(message)
            call.finish()

    def _cancel_asr_call(self):
        call, self._asr_call = self._asr_call, None
        if call is not None:
            call.error = RuntimeError("Final transcription shut down")
            call.finish()

    @pyqtSlot(object)
    def _finished(self, error):
        self.pending -= 1
        if not self.pending:
            # No permanently running QThread when the service is idle. The
            # plain service retains its generation/retry state across dispatches.
            self._thread.quit()
            self._thread.wait()
            self._worker = None
        if error is not None:
            self.failed.emit(str(error))
        self.changed.emit()
        if not self.pending:
            self.idle.emit()

    def close(self):
        # Closing is permanent even when backend ownership cannot be released
        # during this attempt. Service retries/internal track scheduling are
        # rejected by _transcribe without publishing new adapter work.
        self._closed = True
        try:
            adapter_closed = self.adapter.shutdown(0)
        except Exception as exc:
            self.failed.emit(str(exc))
            return False
        if not adapter_closed:
            return False
        self._cancel_asr_call()
        if self.pending:
            return False
        self._thread.quit()
        self._thread.wait()
        return True
