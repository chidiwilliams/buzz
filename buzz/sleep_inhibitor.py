import ctypes
import logging
import os
import platform
import subprocess
import threading
from collections import Counter
from collections.abc import Callable
from typing import Protocol
from uuid import UUID


ES_SYSTEM_REQUIRED = 0x00000001
ES_CONTINUOUS = 0x80000000


class SleepBackend(Protocol):
    def acquire(self) -> None:
        ...

    def release(self) -> None:
        ...


class TaskActivity:
    """Track queued and running tasks and report busy-state transitions."""

    def __init__(self, on_busy_changed: Callable[[bool], None]):
        self._task_counts: Counter[UUID] = Counter()
        self._on_busy_changed = on_busy_changed
        self._lock = threading.Lock()

    def add(self, task_id: UUID) -> None:
        with self._lock:
            was_busy = bool(self._task_counts)
            self._task_counts[task_id] += 1
            if not was_busy:
                self._on_busy_changed(True)

    def finish(self, task_id: UUID) -> None:
        with self._lock:
            was_busy = bool(self._task_counts)
            if self._task_counts[task_id] > 1:
                self._task_counts[task_id] -= 1
            else:
                self._task_counts.pop(task_id, None)
            if was_busy and not self._task_counts:
                self._on_busy_changed(False)

    def clear(self) -> None:
        with self._lock:
            if self._task_counts:
                self._task_counts.clear()
                self._on_busy_changed(False)


class WindowsSleepBackend:
    def __init__(self, set_execution_state=None):
        self._set_execution_state = (
            set_execution_state
            if set_execution_state is not None
            else ctypes.windll.kernel32.SetThreadExecutionState
        )

    def acquire(self) -> None:
        if not self._set_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
            raise OSError("SetThreadExecutionState failed")

    def release(self) -> None:
        if not self._set_execution_state(ES_CONTINUOUS):
            raise OSError("SetThreadExecutionState failed")


class MacOSSleepBackend:
    def __init__(self, popen=subprocess.Popen):
        self._popen = popen
        self._process = None

    def acquire(self) -> None:
        self._process = self._popen(
            ["caffeinate", "-i", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def release(self) -> None:
        if self._process is None:
            return
        process = self._process
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        self._process = None


class NoopSleepBackend:
    def acquire(self) -> None:
        pass

    def release(self) -> None:
        pass


def create_sleep_backend() -> SleepBackend:
    system = platform.system()
    if system == "Windows":
        return WindowsSleepBackend()
    if system == "Darwin":
        return MacOSSleepBackend()
    return NoopSleepBackend()


class SleepInhibitor:
    """Hold a platform sleep assertion while Buzz has pending work."""

    def __init__(self, backend: SleepBackend | None = None, enabled: bool = True):
        self._backend = backend if backend is not None else create_sleep_backend()
        self._enabled = enabled
        self._busy = False
        self.active = False

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._sync()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._sync()

    def close(self) -> None:
        self._busy = False
        self._sync()

    def _sync(self) -> None:
        should_be_active = self._enabled and self._busy
        if should_be_active == self.active:
            return

        try:
            if should_be_active:
                self._backend.acquire()
            else:
                self._backend.release()
        except Exception:
            logging.exception("Failed to update the system sleep assertion")
            return

        self.active = should_be_active
