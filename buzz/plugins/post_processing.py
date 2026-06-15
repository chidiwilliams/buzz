"""
Thread marshaling helpers for running plugin post-processing off the UI thread.

Buzz's database uses a thread-affine ``QSqlDatabase`` default connection, so all
DB access must happen on the main thread. Plugin work (e.g. network calls for an
AI summary) should NOT block the UI, so it runs on a background thread; any DB
access a plugin performs via ``PluginContext.transcription_service`` is
transparently marshaled back to the main thread.
"""

import threading
from typing import Callable

from PyQt6.QtCore import (
    QObject,
    QRunnable,
    QThread,
    QCoreApplication,
    pyqtSignal,
    pyqtSlot,
)


class MainThreadInvoker(QObject):
    """Runs callables on the thread this object lives on (the main thread).

    ``call`` is safe to invoke from any thread: when called off the owning
    thread it schedules the callable via a queued signal and blocks until it
    completes, propagating the return value or exception.
    """

    _scheduled = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scheduled.connect(self._execute)

    @pyqtSlot(object)
    def _execute(self, fn):
        fn()

    def call(self, fn: Callable, *args, **kwargs):
        app = QCoreApplication.instance()
        if app is None or QThread.currentThread() == app.thread():
            return fn(*args, **kwargs)

        box: dict = {}
        done = threading.Event()

        def run():
            try:
                box["value"] = fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - propagated to caller
                box["error"] = exc
            finally:
                done.set()

        self._scheduled.emit(run)
        done.wait()
        if "error" in box:
            raise box["error"]
        return box.get("value")


class MainThreadServiceProxy:
    """Wraps a service so every method call is marshaled to the main thread."""

    def __init__(self, target, invoker: MainThreadInvoker):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_invoker", invoker)

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if callable(attr):
            invoker = object.__getattribute__(self, "_invoker")

            def wrapper(*args, **kwargs):
                return invoker.call(attr, *args, **kwargs)

            return wrapper
        return attr


class FnRunnableSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)


class FnRunnable(QRunnable):
    """Runs an arbitrary callable on the global thread pool with signals."""

    def __init__(self, fn: Callable[[], None]):
        super().__init__()
        self.fn = fn
        self.signals = FnRunnableSignals()

    def run(self):
        try:
            self.fn()
            self.signals.finished.emit()
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))
