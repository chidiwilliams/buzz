import glob
import logging
import multiprocessing
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from typing import List
from unittest.mock import Mock

import psutil
import pytest
from PyQt6.QtCore import QObject, QThread, Qt, pyqtSlot
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import (
    OutputFormat,
    get_output_file_path,
    FileTranscriptionTask,
    TranscriptionOptions,
    Task,
    FileTranscriptionOptions,
    Segment,
)
from buzz.transcriber.whisper_file_transcriber import (
    DetailedWhisperFileTranscriber,
    WhisperFileTranscriber,
    check_file_has_audio_stream,
    terminate_child_processes,
    PROGRESS_REGEX,
)
from tests.audio import test_audio_path
from tests.model_loader import get_model_path


class _LocalArtifactWhisperFileTranscriber(WhisperFileTranscriber):
    """Keep URL-import coverage independent of a downloaded ASR model."""

    def transcribe(self) -> List[Segment]:
        self.progress.emit((0, 100))
        check_file_has_audio_stream(self.transcription_task.file_path)
        self.progress.emit((100, 100))
        return [Segment(start=0, end=100, text="local test transcript")]


@pytest.fixture(scope="session")
def qapp_cls():
    return QApplication


def _spawn_grandchild_worker(pipe):
    """Multiprocessing target that mirrors the whisper.cpp process tree.

    Spawns a long-lived subprocess (the stand-in for ``whisper-cli``), reports
    its pid back to the parent, then blocks waiting on it. This gives us a
    three-level tree (test -> worker process -> subprocess) to verify that
    ``terminate_child_processes`` reaps grandchildren, not just the direct child.
    """
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    pipe.send(proc.pid)
    pipe.close()
    proc.wait()


def _spawn_grandchild_transcriber(pipe, _task):
    """Deterministic stand-in for an ASR worker with a native child process."""
    _spawn_grandchild_worker(pipe)


def _is_dead_or_zombie(proc: psutil.Process) -> bool:
    """True if the process is gone, or a not-yet-reaped zombie."""
    try:
        if not proc.is_running():
            return True
        return proc.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def _wait_until(predicate, timeout: float = 15.0, interval: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class _LifecyclePipe:
    def __init__(self):
        self.closed = False
        self.close_calls = 0
        self.closed_event = Event()

    def close(self):
        self.close_calls += 1
        self.closed = True
        self.closed_event.set()

    def recv(self):
        assert self.closed_event.wait(10), "reader pipe was not closed"
        raise EOFError


class _LifecycleProcess:
    """Only the Process API used by the transcriber's lifecycle, with gates."""

    def __init__(
        self,
        *,
        child_before_gate=False,
        complete=False,
        fail_start=False,
        terminate_completes=True,
    ):
        self.child_before_gate = child_before_gate
        self.complete = complete
        self.fail_start = fail_start
        self.terminate_completes = terminate_completes
        self.start_entered = Event()
        self.allow_start = Event()
        self.join_entered = Event()
        self.wait_entered = Event()
        self.finished = Event()
        self.sentinel = self.finished
        self.timeline = []
        self.pid = None
        self.exitcode = None
        self.alive = False
        self.reaped = False

    def start(self):
        self.timeline.append("start-entered")
        if self.child_before_gate:
            self.alive = True
        self.start_entered.set()
        assert self.allow_start.wait(10), "test did not release startup"
        if self.fail_start:
            raise RuntimeError("controlled start failure")
        self.pid = 12345
        self.alive = True
        self.timeline.append("start-returning")
        if self.complete:
            self.exitcode = 0
            self.alive = False
            self.finished.set()

    def terminate(self):
        self.timeline.append("terminate")
        if not self.terminate_completes:
            return
        self.exitcode = -15
        self.alive = False
        self.finished.set()

    def join(self, timeout=None):
        self.timeline.append("join")
        self.join_entered.set()
        if timeout is not None and not self.finished.is_set():
            return
        assert self.finished.wait(5), "child was not terminated/completed"
        self.reaped = True
        self.timeline.append("reaped")

    def is_alive(self):
        return self.alive

    def kill(self):
        self.timeline.append("kill")
        self.exitcode = -9
        self.alive = False
        self.finished.set()


def _lifecycle_case(monkeypatch, **process_options):
    from buzz.transcriber import whisper_file_transcriber as module

    process = _LifecycleProcess(**process_options)
    pipes = (_LifecyclePipe(), _LifecyclePipe())
    pipe_factory = Mock(return_value=pipes)
    monkeypatch.setattr(module.multiprocessing, "Pipe", pipe_factory)
    monkeypatch.setattr(module.multiprocessing, "Process", lambda **kwargs: process)

    def wait_for_exit(handles):
        assert handles == [process.sentinel]
        process.wait_entered.set()
        assert process.finished.wait(5), "child was not terminated/completed"
        return handles

    monkeypatch.setattr(module, "wait", wait_for_exit)
    monkeypatch.setattr(module.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(
        module,
        "terminate_child_processes",
        lambda pid: process.timeline.append("terminate-descendants"),
    )
    transcriber = WhisperFileTranscriber(
        FileTranscriptionTask(
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(),
            model_path="unused-test-model",
        )
    )
    return transcriber, process, pipes, pipe_factory


def _drive_lifecycle(transcriber):
    outcome = {}

    def run():
        try:
            outcome["result"] = transcriber.transcribe()
        except Exception as exc:
            outcome["error"] = exc

    worker = Thread(target=run, daemon=True)
    worker.start()
    return worker, outcome


def _release_lifecycle(worker, process, pipes):
    """Failure cleanup never satisfies the assertions made before this call."""
    process.allow_start.set()
    process.finished.set()
    for pipe in pipes:
        if not pipe.closed:
            pipe.close()
    worker.join(timeout=10)
    assert not worker.is_alive(), "test worker leaked"


class TestStartupCancellation:
    def test_stop_before_start(self, monkeypatch):
        transcriber, process, pipes, pipe_factory = _lifecycle_case(
            monkeypatch, complete=True
        )
        process.allow_start.set()
        transcriber.stop()
        transcriber.stop()
        with pytest.raises(Exception, match="Transcription was canceled"):
            transcriber.transcribe()
        assert transcriber.stopped
        assert not transcriber.started_process
        assert process.timeline == []
        pipe_factory.assert_not_called()
        assert transcriber.read_line_thread is None

    @pytest.mark.parametrize("child_before_gate", [False, True])
    def test_stop_during_start(self, monkeypatch, child_before_gate):
        transcriber, process, pipes, _ = _lifecycle_case(
            monkeypatch, child_before_gate=child_before_gate
        )
        worker, outcome = _drive_lifecycle(transcriber)
        try:
            assert process.start_entered.wait(5)
            transcriber.stop()
            transcriber.stop()
            assert transcriber.stopped
            assert not transcriber.started_process
            assert process.timeline == ["start-entered"]
            process.timeline.append("stop-requested")
            process.allow_start.set()
            worker.join(timeout=10)
            assert not worker.is_alive(), "pending cancellation was not replayed"
            assert str(outcome.get("error")) == "Transcription was canceled"
            assert process.reaped and not process.is_alive()
            assert process.timeline == [
                "start-entered",
                "stop-requested",
                "start-returning",
                "terminate-descendants",
                "terminate",
                "join",
                "reaped",
            ]
            assert transcriber.read_line_thread is None
            assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
            transcriber.stop()
            assert process.timeline.count("terminate") == 1
            assert process.timeline.count("join") == 1
            assert not transcriber.started_process
        finally:
            _release_lifecycle(worker, process, pipes)

    def test_normal_start_and_completion(self, monkeypatch):
        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch, complete=True)
        process.allow_start.set()
        assert transcriber.transcribe() == []
        assert not transcriber.stopped
        assert not transcriber.started_process
        assert process.timeline == [
            "start-entered",
            "start-returning",
            "join",
            "reaped",
        ]
        assert process.reaped
        assert not transcriber.read_line_thread.is_alive()
        assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
        transcriber.stop()
        assert "terminate" not in process.timeline

    def test_normal_post_start_stop_is_idempotent(self, monkeypatch):
        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch)
        process.allow_start.set()
        worker, outcome = _drive_lifecycle(transcriber)
        try:
            assert process.wait_entered.wait(5)
            assert transcriber.started_process
            transcriber.stop()
            assert process.reaped
            transcriber.stop()
            worker.join(timeout=10)
            assert not worker.is_alive()
            assert str(outcome.get("error")) == "Unknown error"
            assert process.timeline.count("terminate") == 1
            assert process.timeline.count("terminate-descendants") == 1
            assert process.timeline.count("join") == 1
            assert not process.is_alive()
            assert not transcriber.started_process
            assert not transcriber.read_line_thread.is_alive()
            assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
        finally:
            _release_lifecycle(worker, process, pipes)

    def test_start_failure_closes_pipes_and_preserves_error(self, monkeypatch):
        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch, fail_start=True)
        process.allow_start.set()
        with pytest.raises(RuntimeError, match="controlled start failure"):
            transcriber.transcribe()
        assert not transcriber.started_process
        assert "join" not in process.timeline
        assert "terminate" not in process.timeline
        assert transcriber.read_line_thread is None
        assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
        transcriber.stop()
        assert not transcriber._lifecycle_lock._is_owned()
        assert transcriber._cleanup_done.is_set()

    @pytest.mark.parametrize("during_start", [False, True])
    def test_concurrent_stop_during_slow_cleanup(self, monkeypatch, during_start):
        from buzz.transcriber import whisper_file_transcriber as module

        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch)
        cleanup_entered, release_cleanup = Event(), Event()
        stop_returned = Event()
        stop_errors = []
        callers = []

        def slow_descendants(pid):
            process.timeline.append("terminate-descendants")
            cleanup_entered.set()
            # Only the first owner blocks, so an ownership mutation exposes a
            # second destructive caller instead of merely timing out.
            if process.timeline.count("terminate-descendants") == 1:
                assert release_cleanup.wait(10), "test did not release cleanup"

        def stop_again():
            try:
                transcriber.stop()
            except Exception as exc:
                stop_errors.append(exc)
            finally:
                stop_returned.set()

        monkeypatch.setattr(module, "terminate_child_processes", slow_descendants)
        worker, outcome = _drive_lifecycle(transcriber)
        try:
            assert process.start_entered.wait(5)
            if during_start:
                transcriber.stop()
            process.allow_start.set()
            if not during_start:
                assert process.wait_entered.wait(5)
                owner = Thread(target=stop_again, daemon=True)
                callers.append(owner)
                owner.start()
            assert cleanup_entered.wait(5)

            acquired = transcriber._lifecycle_lock.acquire(blocking=False)
            assert acquired, "lifecycle lock held during blocking cleanup"
            transcriber._lifecycle_lock.release()

            second = Thread(target=stop_again, daemon=True)
            callers.append(second)
            second.start()
            assert stop_returned.wait(2), "second stop waited for the cleanup owner"
            assert not stop_errors
            assert process.timeline.count("terminate-descendants") == 1
            assert not process.reaped
            assert not transcriber._cleanup_done.is_set()
            assert all(not pipe.closed for pipe in pipes)

            release_cleanup.set()
            for caller in callers:
                caller.join(timeout=5)
                assert not caller.is_alive()
            worker.join(timeout=5)
            assert not worker.is_alive()
            assert not stop_errors
            assert process.reaped and not process.is_alive()
            assert process.timeline.count("terminate") == 1
            assert process.timeline.count("join") == 1
            assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
            assert transcriber._cleanup_done.is_set()
            assert str(outcome.get("error")) == (
                "Transcription was canceled" if during_start else "Unknown error"
            )
        finally:
            release_cleanup.set()
            _release_lifecycle(worker, process, pipes)
            for caller in callers:
                caller.join(timeout=5)
                assert not caller.is_alive()

    def test_blocking_operations_are_unlocked_including_kill_fallback(
        self, monkeypatch
    ):
        from buzz.transcriber import whisper_file_transcriber as module

        transcriber, process, pipes, _ = _lifecycle_case(
            monkeypatch, terminate_completes=False
        )
        observed = []

        def observe(name, operation):
            def checked(*args, **kwargs):
                assert not transcriber._lifecycle_lock._is_owned(), name
                observed.append(name)
                return operation(*args, **kwargs)

            return checked

        for name in ("start", "terminate", "join", "kill"):
            monkeypatch.setattr(process, name, observe(name, getattr(process, name)))
        for index, pipe in enumerate(pipes):
            monkeypatch.setattr(pipe, "close", observe(f"pipe-{index}", pipe.close))
        monkeypatch.setattr(
            module,
            "terminate_child_processes",
            observe("descendants", module.terminate_child_processes),
        )
        reader_release = Event()
        original_read_line = transcriber.read_line

        def gated_read_line(pipe):
            original_read_line(pipe)
            assert reader_release.wait(10), "test did not release reader"

        monkeypatch.setattr(transcriber, "read_line", gated_read_line)
        worker, outcome = _drive_lifecycle(transcriber)
        try:
            process.allow_start.set()
            assert process.wait_entered.wait(5)
            reader = transcriber.read_line_thread
            original_join = observe("reader-join", reader.join)

            def release_and_join(*args, **kwargs):
                reader_release.set()
                return original_join(*args, **kwargs)

            monkeypatch.setattr(reader, "join", release_and_join)
            transcriber.stop()
            worker.join(timeout=5)
            assert not worker.is_alive()
            assert process.reaped and not process.is_alive()
            assert process.timeline.count("terminate") == 1
            assert process.timeline.count("kill") == 1
            assert process.timeline.count("join") == 2
            assert set(observed) == {
                "start",
                "terminate",
                "join",
                "kill",
                "descendants",
                "pipe-0",
                "pipe-1",
                "reader-join",
            }
            assert reader_release.is_set() and not reader.is_alive()
            assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
            assert "error" in outcome
        finally:
            reader_release.set()
            _release_lifecycle(worker, process, pipes)

    @pytest.mark.parametrize("cancel", [False, True])
    def test_finalization_waits_for_cleanup_owner(self, monkeypatch, cancel):
        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch)
        close_entered, release_close = Event(), Event()
        finalization_waiting = Event()
        owner_errors = []
        original_close = pipes[1].close
        original_wait = transcriber._cleanup_condition.wait

        def observe_finalization_wait(*args, **kwargs):
            finalization_waiting.set()
            return original_wait(*args, **kwargs)

        monkeypatch.setattr(
            transcriber._cleanup_condition, "wait", observe_finalization_wait
        )

        def slow_close():
            close_entered.set()
            assert release_close.wait(10), "test did not release pipe cleanup"
            original_close()

        monkeypatch.setattr(pipes[1], "close", slow_close)

        def stop_owner():
            try:
                transcriber.stop()
            except Exception as exc:
                owner_errors.append(exc)

        owner = None
        worker, outcome = _drive_lifecycle(transcriber)
        try:
            process.allow_start.set()
            assert process.wait_entered.wait(5)
            if cancel:
                owner = Thread(target=stop_owner, daemon=True)
                owner.start()
            else:
                process.alive = False
                process.exitcode = 0
                process.finished.set()
            assert close_entered.wait(5)
            if cancel:
                assert finalization_waiting.wait(5)
            # Either normal finalization or another stop owns cleanup. A new
            # stop must not terminate/reap/close anything for a second time.
            transcriber.stop()
            assert process.timeline.count("terminate") == int(cancel)
            assert worker.is_alive()
            assert not transcriber._cleanup_done.is_set()
            release_close.set()
            worker.join(timeout=5)
            assert not worker.is_alive()
            if cancel:
                assert str(outcome.get("error")) == "Unknown error"
            else:
                assert outcome == {"result": []}
            assert process.reaped
            assert process.timeline.count("join") == 1
            assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
            assert not transcriber.read_line_thread.is_alive()
            assert not owner_errors
        finally:
            release_close.set()
            _release_lifecycle(worker, process, pipes)
            if owner is not None:
                owner.join(timeout=5)
                assert not owner.is_alive()

    def test_failed_cleanup_releases_ownership_for_retry(self, monkeypatch):
        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch)
        terminate = process.terminate

        def fail_once():
            monkeypatch.setattr(process, "terminate", terminate)
            raise RuntimeError("controlled terminate failure")

        monkeypatch.setattr(process, "terminate", fail_once)
        worker, outcome = _drive_lifecycle(transcriber)
        try:
            process.allow_start.set()
            assert process.wait_entered.wait(5)
            with pytest.raises(RuntimeError, match="controlled terminate failure"):
                transcriber.stop()
            assert not transcriber._lifecycle_lock._is_owned()
            assert not transcriber._cleanup_claimed
            assert transcriber.started_process and process.is_alive()
            transcriber.stop()
            worker.join(timeout=5)
            assert not worker.is_alive()
            assert process.reaped and not process.is_alive()
            assert transcriber._cleanup_error is None
            assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
            assert str(outcome.get("error")) == "Unknown error"
        finally:
            _release_lifecycle(worker, process, pipes)

    @pytest.mark.parametrize("failed_resource", ["send_pipe", "reader_join"])
    def test_post_reap_resource_cleanup_retry(self, monkeypatch, failed_resource):
        from buzz.transcriber import whisper_file_transcriber as module

        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch)
        release_finalization, release_reader = Event(), Event()
        original_wait = module.wait
        original_read = transcriber.read_line
        original_close = pipes[1].close
        failure = RuntimeError("controlled post-reap resource failure")
        attempts = []

        def wait_for_finalization(handles):
            result = original_wait(handles)
            assert release_finalization.wait(10), "finalization not released"
            return result

        def gated_reader(pipe):
            original_read(pipe)
            assert release_reader.wait(10), "reader not released"

        def resource_attempt(name):
            assert process.reaped and not process.is_alive()
            assert not transcriber._lifecycle_lock._is_owned()
            process.timeline.append(name)
            attempts.append(name)
            if name == failed_resource and attempts.count(name) == 1:
                raise failure

        def close_send():
            resource_attempt("send_pipe")
            original_close()

        monkeypatch.setattr(module, "wait", wait_for_finalization)
        monkeypatch.setattr(transcriber, "read_line", gated_reader)
        monkeypatch.setattr(pipes[1], "close", close_send)
        worker, outcome = _drive_lifecycle(transcriber)
        try:
            process.allow_start.set()
            assert process.wait_entered.wait(5)
            reader = transcriber.read_line_thread
            original_join = reader.join

            def join_reader(*args, **kwargs):
                resource_attempt("reader_join")
                release_reader.set()
                return original_join(*args, **kwargs)

            monkeypatch.setattr(reader, "join", join_reader)
            with pytest.raises(RuntimeError) as caught:
                transcriber.stop()
            assert caught.value is failure
            assert process.timeline[:6] == [
                "start-entered",
                "start-returning",
                "terminate-descendants",
                "terminate",
                "join",
                "reaped",
            ]
            assert process.timeline[6] == "send_pipe"
            assert process.reaped and not transcriber.started_process
            assert not transcriber._cleanup_claimed
            assert transcriber._cleanup_error is failure
            completed_after_failure = transcriber._cleanup_done.is_set()
            assert transcriber.recv_pipe is pipes[0]
            assert transcriber.send_pipe is pipes[1]
            assert transcriber.read_line_thread is reader
            assert reader.is_alive()
            if failed_resource == "send_pipe":
                assert all(not pipe.closed for pipe in pipes)

            transcriber.stop()
            assert all(
                pipe.closed and pipe.close_calls == 1 for pipe in pipes
            ), "second stop did not retry post-reap resource cleanup"
            assert not reader.is_alive(), "second stop did not finish reader cleanup"
            assert not completed_after_failure, "failed cleanup was marked complete"
            assert attempts.count(failed_resource) == 2
            assert transcriber._cleanup_done.is_set()
            assert not transcriber._cleanup_claimed
            assert transcriber._cleanup_error is None
            timeline = list(process.timeline)
            transcriber.stop()
            assert process.timeline == timeline
            assert process.timeline.count("terminate-descendants") == 1
            assert process.timeline.count("terminate") == 1
            assert process.timeline.count("join") == 1
            release_finalization.set()
            worker.join(timeout=5)
            assert not worker.is_alive()
            assert str(outcome.get("error")) == "Unknown error"
            assert process.timeline == timeline
        finally:
            release_reader.set()
            release_finalization.set()
            _release_lifecycle(worker, process, pipes)

    def test_concurrent_post_reap_resource_retry(self, monkeypatch):
        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch)
        process.allow_start.set()
        process.start()
        transcriber.current_process = process
        transcriber.started_process = True
        transcriber.recv_pipe, transcriber.send_pipe = pipes
        reader = Thread(target=transcriber.read_line, args=(pipes[0],), daemon=True)
        transcriber.read_line_thread = reader
        reader.start()
        original_close = pipes[1].close
        retry_entered, release_retry, second_returned = Event(), Event(), Event()
        failure = RuntimeError("controlled post-reap resource failure")
        attempts = []
        errors = []
        callers = []

        def close_send():
            assert process.reaped
            assert not transcriber._lifecycle_lock._is_owned()
            attempts.append("close")
            if len(attempts) == 1:
                raise failure
            if len(attempts) == 2:
                retry_entered.set()
                assert release_retry.wait(10), "retry not released"
            original_close()

        def stop_again(returned=None):
            try:
                transcriber.stop()
            except BaseException as exc:
                errors.append(exc)
            finally:
                if returned is not None:
                    returned.set()

        monkeypatch.setattr(pipes[1], "close", close_send)
        try:
            with pytest.raises(RuntimeError) as caught:
                transcriber.stop()
            assert caught.value is failure
            assert not transcriber._cleanup_claimed
            assert not transcriber._cleanup_done.is_set()
            owner = Thread(target=stop_again, daemon=True)
            callers.append(owner)
            owner.start()
            assert retry_entered.wait(5)
            assert transcriber._cleanup_claimed
            assert transcriber._cleanup_error is failure
            acquired = transcriber._lifecycle_lock.acquire(blocking=False)
            assert acquired, "retry holds lifecycle lock during pipe close"
            transcriber._lifecycle_lock.release()
            second = Thread(target=stop_again, args=(second_returned,), daemon=True)
            callers.append(second)
            second.start()
            assert second_returned.wait(5)
            assert not errors
            assert len(attempts) == 2, "multiple concurrent retry owners"
            assert all(not pipe.closed for pipe in pipes)
            assert not transcriber._cleanup_done.is_set()
            release_retry.set()
            for caller in callers:
                caller.join(timeout=5)
                assert not caller.is_alive()
            assert not errors
            assert not reader.is_alive()
            assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
            assert transcriber._cleanup_done.is_set()
            assert not transcriber._cleanup_claimed
            assert transcriber._cleanup_error is None
            transcriber.stop()
            assert len(attempts) == 2
            assert process.timeline.count("terminate-descendants") == 1
            assert process.timeline.count("terminate") == 1
            assert process.timeline.count("join") == 1
        finally:
            release_retry.set()
            for caller in callers:
                caller.join(timeout=5)
                assert not caller.is_alive()
            original_close()
            pipes[0].close()
            reader.join(timeout=5)
            assert not reader.is_alive()

    def test_finalization_observes_post_reap_cleanup_failure(self, monkeypatch):
        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch)
        cleanup_entered, release_cleanup, finalization_waiting = (
            Event(),
            Event(),
            Event(),
        )
        original_close = pipes[1].close
        original_wait = transcriber._cleanup_condition.wait
        failure = RuntimeError("controlled post-reap resource failure")
        owner_errors = []

        def fail_close():
            assert process.reaped
            cleanup_entered.set()
            assert release_cleanup.wait(10), "failure not released"
            raise failure

        def observe_wait(*args, **kwargs):
            finalization_waiting.set()
            return original_wait(*args, **kwargs)

        def stop_owner():
            try:
                transcriber.stop()
            except BaseException as exc:
                owner_errors.append(exc)

        monkeypatch.setattr(pipes[1], "close", fail_close)
        monkeypatch.setattr(transcriber._cleanup_condition, "wait", observe_wait)
        worker, outcome = _drive_lifecycle(transcriber)
        owner = None
        try:
            process.allow_start.set()
            assert process.wait_entered.wait(5)
            owner = Thread(target=stop_owner, daemon=True)
            owner.start()
            assert cleanup_entered.wait(5)
            assert finalization_waiting.wait(5)
            release_cleanup.set()
            owner.join(timeout=5)
            worker.join(timeout=5)
            assert not owner.is_alive()
            assert (
                not worker.is_alive()
            ), "finalization waited forever for successful cleanup"
            assert owner_errors == [failure]
            assert outcome.get("error") is failure
            assert not transcriber._cleanup_done.is_set()
            assert not transcriber._cleanup_claimed
            assert not transcriber.started_process
            assert transcriber.read_line_thread.is_alive()
            monkeypatch.setattr(pipes[1], "close", original_close)
            transcriber.stop()
            assert transcriber._cleanup_error is None
            assert transcriber._cleanup_done.is_set()
            assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
            assert not transcriber.read_line_thread.is_alive()
            assert process.timeline.count("join") == 1
            assert process.timeline.count("terminate") == 1
        finally:
            release_cleanup.set()
            monkeypatch.setattr(pipes[1], "close", original_close)
            _release_lifecycle(worker, process, pipes)
            if owner is not None:
                owner.join(timeout=5)
                assert not owner.is_alive()

    def test_normal_finalization_resource_failure_is_retryable(self, monkeypatch):
        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch, complete=True)
        process.allow_start.set()
        original_close = pipes[1].close
        failure = RuntimeError("controlled normal-finalization resource failure")

        def fail_once():
            assert process.reaped
            monkeypatch.setattr(pipes[1], "close", original_close)
            raise failure

        monkeypatch.setattr(pipes[1], "close", fail_once)
        try:
            with pytest.raises(RuntimeError) as caught:
                transcriber.transcribe()
            assert caught.value is failure
            assert not transcriber.started_process
            assert not transcriber._cleanup_done.is_set()
            assert not transcriber._cleanup_claimed
            assert transcriber._cleanup_error is failure
            transcriber.stop()
            transcriber.stop()
            assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
            assert not transcriber.read_line_thread.is_alive()
            assert transcriber._cleanup_done.is_set()
            assert transcriber._cleanup_error is None
            assert process.timeline == [
                "start-entered",
                "start-returning",
                "join",
                "reaped",
            ]
        finally:
            original_close()
            pipes[0].close()
            if transcriber.read_line_thread is not None:
                transcriber.read_line_thread.join(timeout=5)
                assert not transcriber.read_line_thread.is_alive()

    @pytest.mark.parametrize("pending_resource", ["send_pipe", "reader"])
    def test_incomplete_resources_are_retryable(self, monkeypatch, pending_resource):
        from buzz.transcriber import whisper_file_transcriber as module

        transcriber, process, pipes, _ = _lifecycle_case(monkeypatch, complete=True)
        process.allow_start.set()
        original_close = pipes[1].close
        reader = SimpleNamespace(alive=pending_resource == "reader", join_calls=0)

        def join_reader(timeout):
            assert not transcriber._lifecycle_lock._is_owned()
            reader.join_calls += 1
            if reader.join_calls == 2:
                reader.alive = False

        reader.start = lambda: None
        reader.is_alive = lambda: reader.alive
        reader.join = join_reader
        monkeypatch.setattr(module, "Thread", lambda **kwargs: reader)
        if pending_resource == "send_pipe":

            def fail_close():
                monkeypatch.setattr(pipes[1], "close", original_close)
                raise OSError("controlled pipe close failure")

            monkeypatch.setattr(pipes[1], "close", fail_close)
        with pytest.raises(RuntimeError, match="Transcription resources did not close"):
            transcriber.transcribe()
        assert process.reaped and not transcriber.started_process
        assert not transcriber._cleanup_done.is_set()
        assert not transcriber._cleanup_claimed
        transcriber.stop()
        transcriber.stop()
        assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
        assert not reader.is_alive()
        assert reader.join_calls == (2 if pending_resource == "reader" else 0)
        assert transcriber._cleanup_done.is_set()
        assert transcriber._cleanup_error is None
        assert process.timeline == [
            "start-entered",
            "start-returning",
            "join",
            "reaped",
        ]

    def test_qthread_startup_cancellation(self, qtbot, monkeypatch):
        transcriber, process, pipes, _ = _lifecycle_case(
            monkeypatch, child_before_gate=True
        )
        owner = QObject()
        thread = QThread(owner)
        errors = []
        transcriber.moveToThread(thread)
        thread.started.connect(transcriber.run)
        transcriber.error.connect(errors.append)
        transcriber.error.connect(thread.quit)
        transcriber.completed.connect(thread.quit)
        thread.finished.connect(transcriber.deleteLater)
        thread.start()
        try:
            assert process.start_entered.wait(5)
            transcriber.stop()
            assert transcriber.stopped and not transcriber.started_process
            process.allow_start.set()
            qtbot.waitUntil(lambda: not thread.isRunning(), timeout=10000)
            assert errors == ["Transcription was canceled"]
            assert process.reaped and not process.is_alive()
            assert process.timeline.count("terminate") == 1
            assert all(pipe.closed and pipe.close_calls == 1 for pipe in pipes)
        finally:
            process.allow_start.set()
            process.finished.set()
            for pipe in pipes:
                if not pipe.closed:
                    pipe.close()
            thread.quit()
            assert thread.wait(
                10000
            ), "QThread did not finish; no forced termination allowed"

    def test_process_level_natural_exit(self):
        root = Path(__file__).resolve().parents[2]
        node = (
            "tests/transcriber/whisper_file_transcriber_test.py::"
            "TestStartupCancellation::test_qthread_startup_cancellation"
        )
        env = os.environ.copy()
        for key in tuple(env):
            if key.startswith("COV_CORE_") or key == "COVERAGE_PROCESS_START":
                env.pop(key)
        env["PYTEST_ADDOPTS"] = ""
        env["BUZZ_DISABLE_TELEMETRY"] = "1"
        with subprocess.Popen(
            [sys.executable, "-m", "pytest", "-q", node],
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        ) as child:
            try:
                output, _ = child.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                # Windows venv launchers may have a real interpreter child.
                descendants = psutil.Process(child.pid).children(recursive=True)
                for process in reversed(descendants):
                    try:
                        process.kill()
                    except psutil.NoSuchProcess:
                        pass
                child.kill()
                output, _ = child.communicate(timeout=10)
                pytest.fail(
                    f"Child pytest did not exit naturally within 60s:\n{output}"
                )
            assert child.returncode == 0, output
            assert "1 passed" in output, output


class TestMeetingShutdown:
    @staticmethod
    def start_adapter(monkeypatch, transcriber):
        from buzz.meeting import meeting_transcriber_adapter as module
        from buzz.meeting.final_transcription import FinalTranscriptionConfig

        monkeypatch.setattr(module, "WhisperFileTranscriber", lambda **kw: transcriber)
        monkeypatch.setattr(
            TranscriptionModel, "get_local_model_path", lambda self: "model"
        )
        adapter = module.MeetingTrackTranscriber()
        adapter.start("meeting.wav", 16000, FinalTranscriptionConfig())
        return adapter

    def test_normal_completion_destroys_worker_on_owner_thread(
        self, qtbot, monkeypatch
    ):
        transcriber, process, _, _ = _lifecycle_case(monkeypatch, complete=True)
        destroyed_on = []
        transcriber.destroyed.connect(
            lambda: destroyed_on.append(QThread.currentThread()),
            Qt.ConnectionType.DirectConnection,
        )
        adapter = self.start_adapter(monkeypatch, transcriber)
        owner_thread = adapter._thread
        thread_finished = Event()
        owner_thread.finished.connect(
            thread_finished.set, Qt.ConnectionType.DirectConnection
        )
        completed = []
        adapter.track_completed.connect(completed.append)

        process.allow_start.set()
        qtbot.waitUntil(lambda: completed == [[]], timeout=5000)

        assert destroyed_on == [owner_thread]
        assert thread_finished.is_set()
        assert adapter._thread is adapter._transcriber is None

    def test_destruction_timeout_retains_then_retry_succeeds(self, qtbot, monkeypatch):
        entered, release = Event(), Event()

        class GatedDisposalTranscriber(WhisperFileTranscriber):
            @pyqtSlot()
            def dispose_in_owner_thread(self):
                entered.set()
                assert release.wait(10)
                super().dispose_in_owner_thread()

        base, process, pipes, _ = _lifecycle_case(monkeypatch, complete=True)
        transcriber = GatedDisposalTranscriber(base.transcription_task)
        adapter = self.start_adapter(monkeypatch, transcriber)
        owner_thread = adapter._thread
        try:
            process.allow_start.set()
            assert entered.wait(5)
            assert adapter.shutdown(0) is False
            assert adapter._thread is owner_thread
            assert adapter._transcriber is transcriber
            assert not adapter._worker_destroyed.is_set()
            release.set()
            assert adapter.shutdown(5000) is True
            assert adapter._thread is adapter._transcriber is None
            assert adapter.shutdown(0) is True
            assert all(pipe.closed for pipe in pipes)
        finally:
            release.set()
            assert adapter.shutdown(5000)

    @pytest.mark.parametrize("child_before_gate", [False, True])
    def test_startup_timeout_retains_then_replays(
        self, qtbot, monkeypatch, child_before_gate
    ):
        transcriber, process, pipes, _ = _lifecycle_case(
            monkeypatch, child_before_gate=child_before_gate
        )
        adapter = self.start_adapter(monkeypatch, transcriber)
        owner_thread = adapter._thread
        completed, errors = [], []
        adapter.track_completed.connect(completed.append)
        adapter.track_error.connect(errors.append)
        try:
            assert process.start_entered.wait(5)
            assert adapter.shutdown(0) is False
            assert adapter._thread is owner_thread
            assert adapter._transcriber is transcriber
            assert owner_thread.isRunning()
            adapter._on_completed([])
            adapter._on_error("late error")
            assert completed == errors == []
            adapter.start("again.wav", 16000, None)
            assert errors == ["Shutdown requested"]
            process.allow_start.set()
            result = adapter.shutdown(5000)
            assert result is True, (
                adapter._worker_destroyed.is_set(),
                owner_thread.isRunning(),
                transcriber.cleanup_complete,
                adapter._dispose_requested,
                adapter._stop_thread.is_alive(),
            )
            assert process.reaped and all(pipe.closed for pipe in pipes)
            assert process.timeline.count("terminate") == 1
            assert adapter.shutdown(0) is True
        finally:
            process.allow_start.set()
            assert adapter.shutdown(5000)

    def test_cleanup_failure_retains_worker_for_retry(self, qtbot, monkeypatch):
        transcriber, process, _, _ = _lifecycle_case(monkeypatch)
        original_close = transcriber._close_transcription_resources

        def fail(*args, **kwargs):
            raise RuntimeError("controlled cleanup failure")

        monkeypatch.setattr(transcriber, "_close_transcription_resources", fail)
        process.allow_start.set()
        adapter = self.start_adapter(monkeypatch, transcriber)
        owner_thread = adapter._thread
        try:
            assert process.wait_entered.wait(5)
            assert adapter.shutdown(5000) is False
            assert adapter._thread is owner_thread
            assert adapter._transcriber is transcriber
            assert not adapter._worker_destroyed.is_set()
            monkeypatch.setattr(
                transcriber, "_close_transcription_resources", original_close
            )
            assert adapter.shutdown(5000) is True
            assert process.timeline.count("join") == 1
        finally:
            monkeypatch.setattr(
                transcriber, "_close_transcription_resources", original_close
            )
            assert adapter.shutdown(5000)

    def test_parent_disposal_keeps_worker_owned(self, qtbot, monkeypatch):
        from buzz.meeting.meeting_transcriber_adapter import _owned_workers

        transcriber, process, _, _ = _lifecycle_case(monkeypatch)
        adapter = self.start_adapter(monkeypatch, transcriber)
        parent = QObject()
        parent_destroyed = Event()
        parent.destroyed.connect(parent_destroyed.set)
        adapter.setParent(parent)
        owner_thread = adapter._thread
        try:
            assert process.start_entered.wait(5)
            assert adapter.shutdown(0) is False
            assert owner_thread.parent() is None
            parent.deleteLater()
            qtbot.waitUntil(parent_destroyed.is_set, timeout=5000)
            assert (owner_thread, transcriber) in _owned_workers
            assert owner_thread.isRunning()
        finally:
            process.allow_start.set()
            qtbot.waitUntil(adapter._worker_destroyed.is_set, timeout=5000)
            assert owner_thread.wait(5000)
            adapter._release_worker()
            assert (owner_thread, transcriber) not in _owned_workers

    def test_descendant_cleanup_must_be_observed(self, monkeypatch):
        child = Mock()
        parent = Mock()
        parent.children.return_value = [child]
        monkeypatch.setattr(psutil, "Process", lambda pid: parent)
        monkeypatch.setattr(psutil, "wait_procs", lambda procs, timeout: ([], procs))
        with pytest.raises(RuntimeError, match="child processes did not terminate"):
            terminate_child_processes(123)
        child.terminate.assert_called_once()
        child.kill.assert_called_once()

    def test_cross_thread_disposal_is_rejected(self, monkeypatch):
        transcriber, _, _, _ = _lifecycle_case(monkeypatch)
        owner = QThread()
        transcriber.moveToThread(owner)
        with pytest.raises(RuntimeError, match="owning Qt thread"):
            transcriber.dispose_in_owner_thread()


class TestCheckFileHasAudioStream:
    def test_valid_audio_file(self):
        # Should not raise exception for valid audio file
        check_file_has_audio_stream(test_audio_path)

    def test_missing_file(self):
        with pytest.raises(ValueError, match="File not found"):
            check_file_has_audio_stream("/nonexistent/path/to/file.mp3")

    def test_invalid_media_file(self):
        # Create a temporary text file (not a valid media file)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        try:
            temp_file.write(b"This is not a valid media file")
            temp_file.close()
            with pytest.raises(ValueError, match="Invalid media file"):
                check_file_has_audio_stream(temp_file.name)
        finally:
            os.unlink(temp_file.name)


class TestProgressRegex:
    def test_integer_percentage(self):
        match = PROGRESS_REGEX.search("Progress: 50%")
        assert match is not None
        assert match.group() == "50%"

    def test_decimal_percentage(self):
        match = PROGRESS_REGEX.search("Progress: 75.5%")
        assert match is not None
        assert match.group() == "75.5%"

    def test_no_match(self):
        match = PROGRESS_REGEX.search("No percentage here")
        assert match is None

    def test_extract_percentage_value(self):
        line = "Transcription progress: 85%"
        match = PROGRESS_REGEX.search(line)
        assert match is not None
        percentage = int(match.group().strip("%"))
        assert percentage == 85


class TestTerminateChildProcesses:
    def test_kills_grandchild_subprocess(self):
        """The whisper-cli stand-in (a grandchild) must be killed, not orphaned.

        Reproduces the whisper.cpp shape: a multiprocessing worker that spawns
        a long-lived subprocess. terminate_child_processes must kill that
        subprocess while leaving the worker for its owner to reap.
        """
        recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)
        worker = multiprocessing.Process(
            target=_spawn_grandchild_worker, args=(send_pipe,)
        )
        worker.start()
        # Parent doesn't send; close its copy so the pipe isn't kept open.
        send_pipe.close()

        # The worker reports the grandchild pid once the subprocess is up.
        grandchild_pid = recv_pipe.recv()
        recv_pipe.close()

        worker_proc = psutil.Process(worker.pid)
        grandchild_proc = psutil.Process(grandchild_pid)
        assert worker_proc.is_running()
        assert grandchild_proc.is_running()
        # Sanity check the tree is actually nested two levels deep.
        assert grandchild_pid in {
            child.pid for child in worker_proc.children(recursive=True)
        }

        terminate_child_processes(worker.pid)

        # The grandchild must be gone...
        assert _wait_until(
            lambda: _is_dead_or_zombie(grandchild_proc)
        ), "whisper-cli stand-in subprocess was orphaned instead of killed"

        # ...and the worker must still be reapable via multiprocessing (i.e.
        # terminate_child_processes must not have stolen its waitpid()).
        worker.terminate()
        worker.join(timeout=10)
        assert not worker.is_alive()

    def test_missing_pid_is_noop(self):
        # A pid that cannot be a live process must not raise.
        terminate_child_processes(-1)


class TestWhisperFileTranscriber:
    @pytest.mark.parametrize(
        "file_path,output_format,expected_file_path",
        [
            pytest.param(
                "/a/b/c.mp4",
                OutputFormat.SRT,
                "/a/b/c-translate--Whisper-tiny.srt",
                marks=pytest.mark.skipif(platform.system() == "Windows", reason=""),
            ),
            pytest.param(
                "C:\\a\\b\\c.mp4",
                OutputFormat.SRT,
                "C:\\a\\b\\c-translate--Whisper-tiny.srt",
                marks=pytest.mark.skipif(platform.system() != "Windows", reason=""),
            ),
        ],
    )
    def test_default_output_file(
        self,
        file_path: str,
        output_format: OutputFormat,
        expected_file_path: str,
    ):
        file_path = get_output_file_path(
            file_path=file_path,
            language=None,
            task=Task.TRANSLATE,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY,
            ),
            output_format=output_format,
            output_directory="",
            export_file_name_template="{{ input_file_name }}-{{ task }}-{{ language }}-{{ model_type }}-{{ model_size }}",
        )
        assert file_path == expected_file_path

    @pytest.mark.parametrize(
        "file_path,expected_starts_with",
        [
            pytest.param(
                "/a/b/c.mp4",
                "/a/b/c (Translated on ",
                marks=pytest.mark.skipif(platform.system() == "Windows", reason=""),
            ),
            pytest.param(
                "C:\\a\\b\\c.mp4",
                "C:\\a\\b\\c (Translated on ",
                marks=pytest.mark.skipif(platform.system() != "Windows", reason=""),
            ),
        ],
    )
    def test_default_output_file_with_date(
        self, file_path: str, expected_starts_with: str
    ):
        export_file_name_template = (
            "{{ input_file_name }} (Translated on {{ date_time }})"
        )
        srt = get_output_file_path(
            file_path=file_path,
            language=None,
            task=Task.TRANSLATE,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY,
            ),
            output_format=OutputFormat.TXT,
            output_directory="",
            export_file_name_template=export_file_name_template,
        )

        assert srt.startswith(expected_starts_with)
        assert srt.endswith(".txt")

        srt = get_output_file_path(
            file_path=file_path,
            language=None,
            task=Task.TRANSLATE,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY,
            ),
            output_format=OutputFormat.SRT,
            output_directory="",
            export_file_name_template=export_file_name_template,
        )
        assert srt.startswith(expected_starts_with)
        assert srt.endswith(".srt")

    @pytest.mark.parametrize(
        "word_level_timings,extract_speech,expected_segments,model",
        [
            (
                False,
                False,
                [
                    Segment(
                        0,
                        8400,
                        " Bienvenue dans Passe-Relle. Un podcast pensé pour évêiller",
                    )
                ],
                TranscriptionModel(
                    model_type=ModelType.WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
            ),
            (
                True,
                True,
                [Segment(40, 299, " Bien"), Segment(299, 329, "venue dans")],
                TranscriptionModel(
                    model_type=ModelType.WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
            ),
            (
                False,
                False,
                [
                    Segment(
                        0,
                        8517,
                        " Bienvenue dans Passe-Relle. Un podcast pensé pour évêyer la curiosité des apprenances "
                        "et des apprenances de français.",
                    )
                ],
                TranscriptionModel(
                    model_type=ModelType.HUGGING_FACE,
                    hugging_face_model_id="openai/whisper-tiny",
                ),
            ),
            pytest.param(
                False,
                False,
                [
                    Segment(
                        start=0,
                        end=8400,
                        text=" Bienvenue dans Passrel, un podcast pensé pour éveiller la curiosité des apprenances et des apprenances de français.",
                    )
                ],
                TranscriptionModel(
                    model_type=ModelType.FASTER_WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
                marks=pytest.mark.skipif(
                    platform.system() == "Darwin" and platform.machine() == "x86_64",
                    reason="Error with libiomp5 already initialized on GH action runner: https://github.com/chidiwilliams/buzz/actions/runs/4657331262/jobs/8241832087",
                ),
            ),
        ],
    )
    def test_transcribe_from_file(
        self,
        qtbot: QtBot,
        word_level_timings: bool,
        extract_speech: bool,
        expected_segments: List[Segment],
        model: TranscriptionModel,
    ):
        mock_progress = Mock()
        mock_completed = Mock()
        transcription_options = TranscriptionOptions(
            language="fr",
            task=Task.TRANSCRIBE,
            word_level_timings=word_level_timings,
            extract_speech=extract_speech,
            model=model,
        )
        model_path = get_model_path(transcription_options.model)
        file_path = os.path.abspath(test_audio_path)
        file_transcription_options = FileTranscriptionOptions(file_paths=[file_path])

        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=file_path,
                model_path=model_path,
            )
        )
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        with qtbot.wait_signal(
            transcriber.progress, timeout=10 * 6000
        ), qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        # Reports progress at 0, 0 <= progress <= 100, and 100
        assert mock_progress.call_count >= 2
        assert mock_progress.call_args_list[0][0][0] == (0, 100)

        mock_completed.assert_called()
        segments = mock_completed.call_args[0][0]
        assert len(segments) >= 0
        for i, expected_segment in enumerate(segments):
            assert segments[i].start >= 0
            assert segments[i].end > 0
            assert len(segments[i].text) > 0
            logging.debug(f"{segments[i].start} {segments[i].end} {segments[i].text}")

        transcriber.stop()
        time.sleep(3)

    def test_transcribe_from_url(self, qtbot, monkeypatch, tmp_path):
        url = (
            "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3"
        )

        class FakeYoutubeDL:
            extract_calls = []
            download_calls = []

            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def extract_info(self, requested_url, download):
                type(self).extract_calls.append((requested_url, download))
                if requested_url != url:
                    raise ValueError(f"unexpected URL: {requested_url}")
                return {"title": "whisper-french.mp3"}

            @staticmethod
            def sanitize_info(info):
                return info

            def download(self, requested_urls):
                type(self).download_calls.append(tuple(requested_urls))
                if requested_urls != [url]:
                    raise ValueError(f"unexpected URLs: {requested_urls}")
                shutil.copyfile(test_audio_path, self.options["outtmpl"])
                return 0

        monkeypatch.setattr(
            "buzz.transcriber.file_transcriber.YoutubeDL", FakeYoutubeDL
        )

        mock_progress = Mock()
        mock_completed = Mock()
        transcription_options = TranscriptionOptions()
        local_model_path = tmp_path / "local-test-model.pt"
        local_model_path.write_bytes(b"local test model")
        file_transcription_options = FileTranscriptionOptions(url=url)

        transcriber = _LocalArtifactWhisperFileTranscriber(
            task=FileTranscriptionTask(
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                model_path=str(local_model_path),
                url=url,
                source=FileTranscriptionTask.Source.URL_IMPORT,
            )
        )
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        with qtbot.wait_signal(
            transcriber.progress, timeout=10 * 6000
        ), qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        # Reports progress at 0, 0 <= progress <= 100, and 100
        assert mock_progress.call_count >= 2
        assert mock_progress.call_args_list[0][0][0] == (0, 100)

        assert FakeYoutubeDL.extract_calls == [
            (
                "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3",
                False,
            )
        ]
        assert FakeYoutubeDL.download_calls == [
            (
                "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3",
            )
        ]
        assert os.path.isfile(transcriber.transcription_task.file_path)
        assert os.path.getsize(transcriber.transcription_task.file_path) > 0

        mock_completed.assert_called()
        segments = mock_completed.call_args[0][0]
        assert len(segments) >= 0
        for i, expected_segment in enumerate(segments):
            assert segments[i].start >= 0
            assert segments[i].end > 0
            assert len(segments[i].text) > 0
            logging.debug(f"{segments[i].start} {segments[i].end} {segments[i].text}")

        transcriber.stop()
        time.sleep(3)

    def test_transcribe_from_folder_watch_source(self, qtbot):
        file_path = tempfile.mktemp(suffix=".mp3")
        shutil.copy(test_audio_path, file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=[file_path],
            output_formats={OutputFormat.TXT},
        )
        transcription_options = TranscriptionOptions()
        model_path = get_model_path(transcription_options.model)

        output_directory = tempfile.mkdtemp()
        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                model_path=model_path,
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=file_path,
                output_directory=output_directory,
                source=FileTranscriptionTask.Source.FOLDER_WATCH,
            )
        )
        with qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        assert not os.path.isfile(file_path)
        assert os.path.isfile(
            os.path.join(output_directory, os.path.basename(file_path))
        )
        assert len(glob.glob("*.txt", root_dir=output_directory)) > 0

        transcriber.stop()
        time.sleep(3)

    def test_transcribe_from_folder_watch_source_deletes_file(self, qtbot):
        file_path = tempfile.mktemp(suffix=".mp3")
        shutil.copy(test_audio_path, file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=[file_path],
            output_formats={OutputFormat.TXT},
        )
        transcription_options = TranscriptionOptions()
        model_path = get_model_path(transcription_options.model)

        output_directory = tempfile.mkdtemp()
        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                model_path=model_path,
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=file_path,
                original_file_path=file_path,
                output_directory=output_directory,
                source=FileTranscriptionTask.Source.FOLDER_WATCH,
                delete_source_file=True,
            )
        )
        with qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        assert not os.path.isfile(file_path)
        assert not os.path.isfile(
            os.path.join(output_directory, os.path.basename(file_path))
        )
        assert len(glob.glob("*.txt", root_dir=output_directory)) > 0

        transcriber.stop()
        time.sleep(3)

    def test_transcribe_stop(self, monkeypatch):
        output_file_path = os.path.join(tempfile.gettempdir(), "whisper.txt")
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=[test_audio_path]
        )
        transcription_options = TranscriptionOptions()
        monkeypatch.setattr(
            WhisperFileTranscriber,
            "transcribe_whisper",
            staticmethod(_spawn_grandchild_transcriber),
        )

        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                model_path="unused-test-model",
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=test_audio_path,
            )
        )

        # run() blocks until transcription finishes, so drive it from a thread
        # and stop it mid-flight from the test thread.
        run_thread = Thread(target=transcriber.run, daemon=True)
        run_thread.start()

        # Wait until the worker process and its stand-in native subprocess are up.
        def worker_tree_is_up() -> bool:
            if not transcriber.started_process:
                return False
            pid = transcriber.current_process.pid
            if pid is None:
                return False
            try:
                return len(psutil.Process(pid).children(recursive=True)) > 0
            except psutil.NoSuchProcess:
                return False

        assert _wait_until(
            worker_tree_is_up, timeout=60
        ), "worker/subprocess did not start"

        worker_pid = transcriber.current_process.pid
        worker_proc = psutil.Process(worker_pid)
        descendants = worker_proc.children(recursive=True)
        assert descendants, "stand-in subprocess did not start"

        transcriber.stop()

        # run() must return promptly and the whole process tree must be gone.
        run_thread.join(timeout=30)
        assert (
            not run_thread.is_alive()
        ), "transcriber.run() did not return after stop()"

        assert _wait_until(lambda: _is_dead_or_zombie(worker_proc))
        for child in descendants:
            assert _wait_until(
                lambda child=child: _is_dead_or_zombie(child)
            ), f"stand-in subprocess {child.pid} still running after stop()"

        # Assert that file was not created
        assert os.path.isfile(output_file_path) is False


class TestTranscribeFasterWhisper:
    def test_raises_when_model_path_is_empty(self):
        task = FileTranscriptionTask(
            model_path="",
            transcription_options=TranscriptionOptions(
                model=TranscriptionModel(
                    model_type=ModelType.FASTER_WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                )
            ),
            file_transcription_options=FileTranscriptionOptions(
                file_paths=[test_audio_path]
            ),
            file_path=test_audio_path,
        )
        with pytest.raises(FileNotFoundError, match="BUZZ_MODEL_ROOT"):
            WhisperFileTranscriber.transcribe_faster_whisper(task)

        time.sleep(3)


def _detailed_task(
    model_type: ModelType, *, word_level_timings: bool = True
) -> FileTranscriptionTask:
    return FileTranscriptionTask(
        model_path="local-model",
        transcription_options=TranscriptionOptions(
            language="zh",
            task=Task.TRANSCRIBE,
            word_level_timings=word_level_timings,
            initial_prompt="",
            model=TranscriptionModel(
                model_type=model_type,
                whisper_model_size=WhisperModelSize.SMALL,
            ),
        ),
        file_transcription_options=FileTranscriptionOptions(output_formats=set()),
        file_path="meeting.wav",
    )


class TestDetailedWhisperResult:
    def test_openai_whisper_preserves_native_phrase_and_words_one_inference(
        self, monkeypatch
    ) -> None:
        raw_result = SimpleNamespace(
            segments=[
                SimpleNamespace(
                    start=1.0,
                    end=2.5,
                    text=" phrase text ",
                    words=[
                        SimpleNamespace(start=1.0, end=1.4, word=" first "),
                        SimpleNamespace(start=1.3, end=1.8, word=" second "),
                        SimpleNamespace(start=1.8, end=1.9, word="   "),
                    ],
                )
            ]
        )
        model = Mock()
        model.transcribe.return_value = raw_result
        monkeypatch.setattr(
            WhisperFileTranscriber,
            "_load_openai_whisper_model",
            Mock(return_value=model),
        )
        modify_model = Mock()
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.stable_whisper.modify_model",
            modify_model,
        )
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.whisper_audio.load_audio",
            Mock(return_value="pcm"),
        )

        result = WhisperFileTranscriber.transcribe_openai_whisper_detailed(
            _detailed_task(ModelType.WHISPER)
        )

        assert model.transcribe.call_count == 1
        assert len(result.segments) == 1
        assert result.segments[0].text == " phrase text "
        assert [word.text for word in result.words] == ["first", "second"]
        assert [word.source_segment_ordinal for word in result.words] == [0, 0]
        assert (result.words[1].start_ms, result.words[1].end_ms) == (1300, 1800)
        options = model.transcribe.call_args.kwargs
        assert options["temperature"] == (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
        assert options["beam_size"] == 5
        assert options["best_of"] == 5
        assert options["patience"] == 1.0
        modify_model.assert_called_once_with(model)

    def test_faster_preserves_native_phrase_and_words_one_inference(
        self, monkeypatch
    ) -> None:
        raw_segment = SimpleNamespace(
            start=0.5,
            end=2.0,
            text=" native phrase ",
            words=(
                SimpleNamespace(start=0.5, end=1.0, word=" one "),
                SimpleNamespace(start=0.9, end=1.4, word=" two "),
            ),
        )
        pipeline = Mock()
        pipeline.transcribe.return_value = (iter((raw_segment,)), SimpleNamespace())
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.faster_whisper.WhisperModel",
            Mock(return_value=Mock()),
        )
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.faster_whisper.BatchedInferencePipeline",
            Mock(return_value=pipeline),
        )
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.whisper_audio.load_audio",
            Mock(return_value="pcm"),
        )
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.torch.cuda.is_available",
            Mock(return_value=False),
        )

        result = WhisperFileTranscriber.transcribe_faster_whisper_detailed(
            _detailed_task(ModelType.FASTER_WHISPER)
        )

        assert pipeline.transcribe.call_count == 1
        assert len(result.segments) == 1
        assert result.segments[0].text == " native phrase "
        assert [word.text for word in result.words] == ["one", "two"]
        assert result.words[0].source_segment_ordinal == 0
        options = pipeline.transcribe.call_args.kwargs
        assert options["word_timestamps"] is True
        assert options["temperature"] == 0.0
        assert options["beam_size"] == 5
        assert options["best_of"] == 5
        assert options["patience"] == 1.0

    def test_ordinary_openai_word_path_keeps_v1_options(self, monkeypatch) -> None:
        raw_result = SimpleNamespace(
            segments=[
                SimpleNamespace(
                    words=[SimpleNamespace(start=0.0, end=0.5, word=" word ")]
                )
            ]
        )
        model = Mock()
        model.transcribe.return_value = raw_result
        monkeypatch.setattr(
            WhisperFileTranscriber,
            "_load_openai_whisper_model",
            Mock(return_value=model),
        )
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.stable_whisper.modify_model",
            Mock(),
        )
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.whisper_audio.load_audio",
            Mock(return_value="pcm"),
        )

        segments = WhisperFileTranscriber.transcribe_openai_whisper(
            _detailed_task(ModelType.WHISPER)
        )

        assert [segment.text for segment in segments] == ["word"]
        options = model.transcribe.call_args.kwargs
        assert "beam_size" not in options
        assert "best_of" not in options
        assert "patience" not in options

    def test_ordinary_faster_path_keeps_v1_options(self, monkeypatch) -> None:
        raw_segment = SimpleNamespace(
            start=0.0,
            end=1.0,
            text="phrase",
            words=None,
        )
        pipeline = Mock()
        pipeline.transcribe.return_value = (iter((raw_segment,)), SimpleNamespace())
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.faster_whisper.WhisperModel",
            Mock(return_value=Mock()),
        )
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.faster_whisper.BatchedInferencePipeline",
            Mock(return_value=pipeline),
        )
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.whisper_audio.load_audio",
            Mock(return_value="pcm"),
        )
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.torch.cuda.is_available",
            Mock(return_value=False),
        )
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.platform.system",
            Mock(return_value="Windows"),
        )

        segments = WhisperFileTranscriber.transcribe_faster_whisper(
            _detailed_task(
                ModelType.FASTER_WHISPER,
                word_level_timings=False,
            )
        )

        assert [segment.text for segment in segments] == ["phrase"]
        options = pipeline.transcribe.call_args.kwargs
        assert options["temperature"] == 0
        assert options["word_timestamps"] is False
        assert "beam_size" not in options
        assert "best_of" not in options
        assert "patience" not in options

    def test_detailed_worker_rejects_non_v2_backend(self, monkeypatch) -> None:
        messages: list[str] = []
        connection = Mock()
        connection.send.side_effect = messages.append
        monkeypatch.setattr(
            "buzz.transcriber.whisper_file_transcriber.check_file_has_audio_stream",
            Mock(),
        )

        task = _detailed_task(ModelType.WHISPER_CPP)
        with pytest.raises(Exception, match="does not support"):
            DetailedWhisperFileTranscriber._transcribe_whisper_worker(
                connection, task, detailed=True
            )

        assert any(message.startswith("error = ") for message in messages)
