"""Deterministic tests for ``MeetingWorkflow``.

No Qt, no QSql, no real microphone, no real Windows helper,
no network, no Whisper.  Uses real ``MeetingAudioTracks`` /
``MeetingSession`` / ``MeetingRecorder`` with ``tmp_path``
and ``ControlledAudioSource`` fakes.
"""

from __future__ import annotations

import ast
import pathlib
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import pytest

from buzz.audio_capture.source import (
    AudioErrorCallback,
    AudioFrameCallback,
    AudioSource,
    AudioSourceError,
)
from buzz.meeting.meeting_audio_tracks import (
    MeetingAudioTracksOutcome,
    MeetingAudioTracksState,
)
from buzz.meeting.meeting_session import (
    MeetingRemoteSourceKind,
    MeetingSessionState,
)
from buzz.meeting.meeting_storage import (
    MeetingPersistenceBundle,
    MeetingStorage,
    MeetingStorageCollisionError,
    MeetingStorageDatabaseError,
)
from buzz.meeting.meeting_workflow import (
    MeetingWorkflow,
    MeetingWorkflowError,
    MeetingWorkflowPersistenceError,
    MeetingWorkflowPersistenceInProgressError,
    MeetingWorkflowStartError,
    MeetingWorkflowState,
    MeetingWorkflowStateError,
    MeetingWorkflowStopError,
)


# ---------------------------------------------------------------------------
# Qt import guard
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def cleanup_test_workflows(monkeypatch):
    """Ownership assertions may leave capture active; release it after the test.

    Real recorders use non-daemon writers, so omitting this cleanup prevents
    pytest from exiting even when all assertions pass.
    """
    workflows = []
    initialize = MeetingWorkflow.__init__

    def track(workflow, *args, **kwargs):
        initialize(workflow, *args, **kwargs)
        workflows.append(workflow)

    monkeypatch.setattr(MeetingWorkflow, "__init__", track)
    yield
    for workflow in workflows:
        for _ in range(3):
            try:
                if workflow.state is MeetingWorkflowState.ACTIVE:
                    workflow.stop_capture()
                elif workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED:
                    workflow.retry_cleanup()
                else:
                    break
            except MeetingWorkflowStopError:
                continue
        assert workflow.state not in (
            MeetingWorkflowState.ACTIVE,
            MeetingWorkflowState.CLEANUP_REQUIRED,
        )


def test_no_pyqt_import_in_workflow_module() -> None:
    """``meeting_workflow.py`` must not import PyQt6."""
    source_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "buzz"
        / "meeting"
        / "meeting_workflow.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            names = [alias.name for alias in getattr(node, "names", [])]
            all_names = module + " " + " ".join(names)
            assert (
                "PyQt6" not in all_names
            ), f"meeting_workflow.py imports PyQt6: {all_names}"
            assert "QObject" not in all_names
            assert "pyqtSignal" not in all_names
            assert "QThread" not in all_names


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class ControlledAudioSource(AudioSource):
    """Deterministic audio source for workflow tests.

    Mirrors the ``ControlledAudioSource`` from
    ``meeting_audio_tracks_test.py`` with a focused API surface.
    """

    def __init__(
        self,
        sample_rate: int = 16_000,
        *,
        start_error: Optional[Exception] = None,
        pause_start: bool = False,
    ) -> None:
        self._sample_rate = sample_rate
        self.on_audio: Optional[AudioFrameCallback] = None
        self.on_error: Optional[AudioErrorCallback] = None
        self.start_error = start_error
        self.stop_errors: list[Exception] = []
        self.active = False
        self.start_count = 0
        self.stop_count = 0
        self.start_entered = threading.Event()
        self.allow_start = threading.Event()
        self.stop_entered = threading.Event()
        self.allow_stop = threading.Event()
        self.pause_start = pause_start
        self.pause_stop = False
        self._lock = threading.Lock()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def start(
        self,
        on_audio: AudioFrameCallback,
        on_error: Optional[AudioErrorCallback] = None,
    ) -> None:
        with self._lock:
            self.on_audio = on_audio
            self.on_error = on_error
            self.active = True
            self.start_count += 1
        self.start_entered.set()
        if self.pause_start:
            assert self.allow_start.wait(timeout=5)
        if self.start_error is not None:
            raise self.start_error

    def stop(self) -> None:
        self.stop_entered.set()
        if self.pause_stop:
            assert self.allow_stop.wait(timeout=5)
        with self._lock:
            if self.stop_errors:
                raise self.stop_errors.pop(0)
            if self.active:
                self.active = False
                self.stop_count += 1

    def deliver(self, samples: np.ndarray) -> None:
        with self._lock:
            callback = self.on_audio
            active = self.active
        assert active and callback is not None
        callback(samples)

    def fail(self, error: Exception) -> None:
        with self._lock:
            callback = self.on_error
        assert callback is not None
        callback(error)


class MemoryRepository:
    """In-memory ``MeetingRepository`` for tests."""

    def __init__(self) -> None:
        self.bundles: dict[str, MeetingPersistenceBundle] = {}

    def atomic_replace(self, bundle, *, validate_existing) -> None:
        validate_existing(self.bundles.get(bundle.session_id))
        self.bundles[bundle.session_id] = bundle

    def load_bundle(self, session_id):
        return self.bundles.get(session_id)


class FailingSaveRepository(MemoryRepository):
    """Repository whose ``atomic_replace`` always fails."""

    def atomic_replace(self, bundle, *, validate_existing) -> None:
        raise MeetingStorageDatabaseError("simulated database failure")


class FailingSaveOnceRepository(MemoryRepository):
    """Repository whose ``atomic_replace`` fails the first call only."""

    def __init__(self) -> None:
        super().__init__()
        self._fail_count = 0

    def atomic_replace(self, bundle, *, validate_existing) -> None:
        self._fail_count += 1
        if self._fail_count == 1:
            raise MeetingStorageDatabaseError("simulated first-save failure")
        super().atomic_replace(bundle, validate_existing=validate_existing)


class BlockingSaveRepository(MemoryRepository):
    """Repository whose ``atomic_replace`` blocks on an Event."""

    def __init__(self) -> None:
        super().__init__()
        self.save_entered = threading.Event()
        self.allow_save = threading.Event()

    def atomic_replace(self, bundle, *, validate_existing) -> None:
        self.save_entered.set()
        assert self.allow_save.wait(timeout=5)
        super().atomic_replace(bundle, validate_existing=validate_existing)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow(
    tmp_path: Path, repo=None
) -> tuple[MeetingWorkflow, MemoryRepository]:
    if repo is None:
        repo = MemoryRepository()
    storage = MeetingStorage(repo, root=tmp_path)
    return MeetingWorkflow(storage), repo


def _small_pcm(n: int = 160) -> np.ndarray:
    """Small deterministic mono float32 block."""
    return np.zeros(n, dtype=np.float32)


def _deliver_both(
    mic: ControlledAudioSource,
    remote: ControlledAudioSource,
    n: int = 160,
) -> None:
    mic.deliver(_small_pcm(n))
    remote.deliver(_small_pcm(n))


def _wait_for_audio_delivery(
    source: ControlledAudioSource, timeout: float = 5.0
) -> None:
    """Wait until a source's on_audio callback is registered by the
    producer thread.  Bounded polling with a deadlock-guard timeout.

    The producer thread registers its callback sometime after the
    source's ``start()`` method returns.  We poll for ``on_audio``
    being non-None and ``active`` being True as a readiness signal.
    This is a deadlock guard, not a correctness mechanism — the
    caller delivers audio *after* this returns.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with source._lock:
            if source.on_audio is not None and source.active:
                return
        time.sleep(0.005)
    raise TimeoutError(
        f"Timed out waiting for source on_audio callback (timeout={timeout}s)"
    )


def _start_and_activate(
    tmp_path: Path,
    *,
    repo=None,
    mic: Optional[ControlledAudioSource] = None,
    remote: Optional[ControlledAudioSource] = None,
) -> tuple[
    MeetingWorkflow, ControlledAudioSource, ControlledAudioSource, MemoryRepository
]:
    """Start a workflow and deliver one audio block to both sources.

    Returns (workflow, mic_source, remote_source, repo) in ACTIVE state.
    """
    workflow, repo = _make_workflow(tmp_path, repo)
    if mic is None:
        mic = ControlledAudioSource()
    if remote is None:
        remote = ControlledAudioSource()
    workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
    # Wait for both sources to start.
    mic.start_entered.wait(timeout=5)
    remote.start_entered.wait(timeout=5)
    # Wait until the recorder has registered its audio callback, then
    # deliver samples.  This avoids a fixed-sleep correctness dependency.
    _wait_for_audio_delivery(mic)
    _wait_for_audio_delivery(remote)
    _deliver_both(mic, remote)
    return workflow, mic, remote, repo


# ---------------------------------------------------------------------------
# §39 Core integration: full end-to-end lifecycle
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    """Full prepare → start → deliver → stop → persist lifecycle."""

    def test_happy_path(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        assert workflow.state is MeetingWorkflowState.ACTIVE
        sid = workflow.session_id
        assert sid is not None

        # Stop
        stop_result = workflow.stop_capture()
        assert stop_result.cleanup_succeeded is True
        assert stop_result.snapshot.state is MeetingSessionState.COMPLETED
        assert stop_result.audio is not None
        assert stop_result.audio.outcome in (
            MeetingAudioTracksOutcome.COMPLETE,
            MeetingAudioTracksOutcome.PARTIAL,
        )
        assert workflow.state is MeetingWorkflowState.AWAITING_PERSISTENCE

        # Persist
        persist_result = workflow.persist()
        assert persist_result.session_id == sid
        assert persist_result.stored_meeting.session_id == sid
        assert workflow.state is MeetingWorkflowState.IDLE
        assert workflow.session_id is None

    def test_persist_returns_stored_meeting_with_correct_state(
        self, tmp_path: Path
    ) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        workflow.stop_capture()
        persist = workflow.persist()
        stored = persist.stored_meeting
        assert stored.state is MeetingSessionState.COMPLETED
        assert stored.microphone is not None
        assert stored.remote is not None
        assert stored.audio_outcome is not None

    def test_workflow_reusable_after_persist(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        first_session_id = workflow.session_id
        workflow.stop_capture()
        workflow.persist()
        assert workflow.state is MeetingWorkflowState.IDLE
        assert not workflow.is_active
        # Can start a new meeting with a distinct session ID.
        mic2 = ControlledAudioSource()
        remote2 = ControlledAudioSource()
        result = workflow.start_capture(
            mic2, remote2, MeetingRemoteSourceKind.APPLICATION
        )
        assert result.session_id != first_session_id
        assert workflow.session_id == result.session_id
        assert workflow.state is MeetingWorkflowState.ACTIVE


# ---------------------------------------------------------------------------
# §40 Start ordering oracle
# ---------------------------------------------------------------------------


class TestStartOrdering:
    """Storage prepare must happen before source start."""

    def test_prepare_precedes_source_start(self, tmp_path: Path) -> None:
        """Verify prepare is called before sources start by checking
        that the session directory exists when sources start."""
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource()

        directory_existed_at_start = threading.Event()
        original_mic_start = mic.start

        def instrumented_mic_start(on_audio, on_error=None):
            # The session directory should exist at this point because
            # prepare() was already called.
            sid = workflow.session_id
            assert sid is not None
            session_dir = tmp_path / str(sid)
            if session_dir.is_dir():
                directory_existed_at_start.set()
            original_mic_start(on_audio, on_error)

        mic.start = instrumented_mic_start  # type: ignore[assignment]

        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        assert directory_existed_at_start.is_set()


# ---------------------------------------------------------------------------
# §41 Identity oracle
# ---------------------------------------------------------------------------


class TestIdentityOracle:
    """Same UUID flows through prepare → session → persist."""

    def test_same_uuid_throughout(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        sid = workflow.session_id
        assert sid is not None

        # Verify session snapshot uses the same UUID.
        snap = workflow.snapshot()
        assert snap is not None
        assert snap.session_id == sid

        # Stop and verify.
        workflow.stop_capture()
        snap = workflow.snapshot()
        assert snap is not None
        assert snap.session_id == sid

        # Persist and verify.
        persist = workflow.persist()
        assert persist.session_id == sid
        assert persist.stored_meeting.session_id == sid


# ---------------------------------------------------------------------------
# §42 Path oracle
# ---------------------------------------------------------------------------


class TestPathOracle:
    """Archive files use paths returned by MeetingStorage.prepare()."""

    def test_output_paths_match_prepare(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource()

        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        sid = workflow.session_id
        assert sid is not None

        # Verify the session directory exists and follows the expected layout.
        expected_dir = tmp_path.resolve() / str(sid)
        assert expected_dir.is_dir()
        # Paths follow the canonical layout: <root>/<session_id>/<role>.wav
        assert (expected_dir / "microphone.wav").name == "microphone.wav"
        assert (expected_dir / "remote.wav").name == "remote.wav"

    def test_persist_stored_paths_match_prepare(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        workflow.stop_capture()
        persist = workflow.persist()
        stored = persist.stored_meeting
        sid = persist.session_id
        expected_dir = tmp_path.resolve() / str(sid)
        assert stored.microphone is not None
        assert stored.remote is not None
        assert stored.microphone.path == expected_dir / "microphone.wav"
        assert stored.remote.path == expected_dir / "remote.wav"


# ---------------------------------------------------------------------------
# §43 Double-start oracle
# ---------------------------------------------------------------------------


class TestDoubleStart:
    """Second start while active must fail without side effects."""

    def test_second_start_rejected(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)

        mic2 = ControlledAudioSource()
        remote2 = ControlledAudioSource()

        with pytest.raises(MeetingWorkflowStateError, match="ACTIVE"):
            workflow.start_capture(mic2, remote2, MeetingRemoteSourceKind.SYSTEM)

        # Second sources never started.
        assert mic2.start_count == 0
        assert remote2.start_count == 0
        # First meeting still active.
        assert workflow.state is MeetingWorkflowState.ACTIVE

    def test_second_start_rejected_during_starting(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource(pause_start=True)
        remote = ControlledAudioSource(pause_start=True)

        # Start in background — stays in STARTING while paused.
        started = threading.Event()
        start_error: list[Exception] = []

        def do_start():
            try:
                workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
            except Exception as exc:
                start_error.append(exc)
            finally:
                started.set()

        t = threading.Thread(target=do_start)
        t.start()

        # Wait until we're in STARTING.
        mic.start_entered.wait(timeout=5)
        assert workflow.state is MeetingWorkflowState.STARTING

        # Second start must fail.
        mic2 = ControlledAudioSource()
        remote2 = ControlledAudioSource()
        with pytest.raises(MeetingWorkflowStateError):
            workflow.start_capture(mic2, remote2, MeetingRemoteSourceKind.SYSTEM)
        assert mic2.start_count == 0

        # Allow first start to complete.
        mic.allow_start.set()
        remote.allow_start.set()
        started.wait(timeout=5)
        t.join(timeout=5)

        # Clean up.
        try:
            workflow.stop_capture()
        except MeetingWorkflowStopError:
            pass
        try:
            workflow.persist()
        except Exception:
            pass

    def test_second_start_rejected_during_cleanup_required(
        self, tmp_path: Path
    ) -> None:
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)

        # Force a stop failure by injecting stop errors on the sources.
        mic.stop_errors = [RuntimeError("mic stop failed")]
        remote.stop_errors = [RuntimeError("remote stop failed")]

        try:
            workflow.stop_capture()
        except MeetingWorkflowStopError:
            pass

        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED

        # Second start must fail.
        mic2 = ControlledAudioSource()
        remote2 = ControlledAudioSource()
        with pytest.raises(MeetingWorkflowStateError, match="CLEANUP_REQUIRED"):
            workflow.start_capture(mic2, remote2, MeetingRemoteSourceKind.SYSTEM)
        assert mic2.start_count == 0


# ---------------------------------------------------------------------------
# §44 Normal stop oracle
# ---------------------------------------------------------------------------


class TestNormalStop:
    """Successful stop produces COMPLETED snapshot."""

    def test_stop_completes(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        result = workflow.stop_capture()
        assert result.cleanup_succeeded is True
        assert result.snapshot.state is MeetingSessionState.COMPLETED
        assert result.audio is not None

    def test_stop_transitions_to_awaiting_persistence(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        workflow.stop_capture()
        assert workflow.state is MeetingWorkflowState.AWAITING_PERSISTENCE

    def test_stop_then_persist_returns_to_idle(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        workflow.stop_capture()
        workflow.persist()
        assert workflow.state is MeetingWorkflowState.IDLE


# ---------------------------------------------------------------------------
# §45 Double-stop semantics
# ---------------------------------------------------------------------------


class TestDoubleStop:
    """Repeated stop must not corrupt state."""

    def test_stop_rejected_when_idle(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        with pytest.raises(MeetingWorkflowStateError):
            workflow.stop_capture()

    def test_stop_rejected_after_persist(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        workflow.stop_capture()
        workflow.persist()
        with pytest.raises(MeetingWorkflowStateError):
            workflow.stop_capture()

    def test_persist_rejected_when_awaiting_persistence(self, tmp_path: Path) -> None:
        """Calling persist again after successful persist fails."""
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        workflow.stop_capture()
        workflow.persist()
        with pytest.raises(MeetingWorkflowStateError):
            workflow.persist()


# ---------------------------------------------------------------------------
# §46 Partial outcome oracle
# ---------------------------------------------------------------------------


class TestPartialOutcome:
    """PARTIAL audio outcome is preserved, not discarded."""

    def test_partial_outcome_preserved(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource(start_error=RuntimeError("remote boom"))

        # start_capture should fail because remote fails.
        with pytest.raises(MeetingWorkflowStartError) as exc_info:
            workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)

        snapshot = exc_info.value.snapshot
        # The snapshot may have audio info from the partial mic track.
        # At minimum the session existed and failed.
        assert snapshot.state in (
            MeetingSessionState.FAILED,
            MeetingSessionState.STARTING,
        )
        # Workflow retains ownership for persistence.
        assert workflow.state in (
            MeetingWorkflowState.AWAITING_PERSISTENCE,
            MeetingWorkflowState.CLEANUP_REQUIRED,
        )
        assert workflow.session_id is not None

    def test_one_track_failure_allows_persistence(self, tmp_path: Path) -> None:
        """When start fails, the snapshot is persistable through the workflow."""
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource(start_error=RuntimeError("remote fail"))

        with pytest.raises(MeetingWorkflowStartError) as exc_info:
            workflow.start_capture(mic, remote, MeetingRemoteSourceKind.APPLICATION)

        snapshot = exc_info.value.snapshot
        assert snapshot.session_id == workflow.session_id
        assert snapshot.state is MeetingSessionState.FAILED

        # The snapshot IS persistable through the workflow API.
        persist = workflow.persist()
        assert persist.session_id == snapshot.session_id
        assert persist.stored_meeting.session_id == snapshot.session_id
        assert workflow.state is MeetingWorkflowState.IDLE


# ---------------------------------------------------------------------------
# §47 Start failure oracle
# ---------------------------------------------------------------------------


class TestStartFailure:
    """Start failure surfaces real snapshot, retains ownership."""

    def test_start_failure_retains_ownership(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        bad_source = ControlledAudioSource(
            start_error=AudioSourceError("hardware gone")
        )
        good_source = ControlledAudioSource()

        with pytest.raises(MeetingWorkflowStartError):
            workflow.start_capture(
                bad_source, good_source, MeetingRemoteSourceKind.SYSTEM
            )
        # Ownership retained — not IDLE.
        assert workflow.state is not MeetingWorkflowState.IDLE
        assert workflow.session_id is not None
        assert workflow.is_active

    def test_start_failure_preserves_real_snapshot(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        bad_source = ControlledAudioSource(
            start_error=RuntimeError("source init failed")
        )
        good_source = ControlledAudioSource()

        with pytest.raises(MeetingWorkflowStartError) as exc_info:
            workflow.start_capture(
                bad_source, good_source, MeetingRemoteSourceKind.SYSTEM
            )

        snap = exc_info.value.snapshot
        assert snap.state is MeetingSessionState.FAILED
        assert snap.audio is not None

    def test_start_failure_no_false_success(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        bad_source = ControlledAudioSource(start_error=RuntimeError("fail"))
        good_source = ControlledAudioSource()

        with pytest.raises(MeetingWorkflowStartError):
            workflow.start_capture(
                bad_source, good_source, MeetingRemoteSourceKind.SYSTEM
            )

        # Must not be in ACTIVE.
        assert workflow.state is not MeetingWorkflowState.ACTIVE
        # Ownership retained — not IDLE.
        assert workflow.state is not MeetingWorkflowState.IDLE

    def test_start_failure_blocks_new_meeting(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        bad_source = ControlledAudioSource(start_error=RuntimeError("fail"))
        good_source = ControlledAudioSource()

        with pytest.raises(MeetingWorkflowStartError):
            workflow.start_capture(
                bad_source, good_source, MeetingRemoteSourceKind.SYSTEM
            )

        # Second start is rejected — ownership retained.
        mic2 = ControlledAudioSource()
        remote2 = ControlledAudioSource()
        with pytest.raises(MeetingWorkflowStateError):
            workflow.start_capture(mic2, remote2, MeetingRemoteSourceKind.SYSTEM)
        assert mic2.start_count == 0
        assert remote2.start_count == 0
        # Original session_id unchanged.
        assert workflow.session_id is not None

    def test_start_failure_then_persist_then_new_meeting(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        bad_source = ControlledAudioSource(start_error=RuntimeError("fail"))
        good_source = ControlledAudioSource()

        with pytest.raises(MeetingWorkflowStartError):
            workflow.start_capture(
                bad_source, good_source, MeetingRemoteSourceKind.SYSTEM
            )

        # Persist the failed meeting.
        assert workflow.state is MeetingWorkflowState.AWAITING_PERSISTENCE
        persist_result = workflow.persist()
        assert persist_result.stored_meeting.state is MeetingSessionState.FAILED
        assert workflow.state is MeetingWorkflowState.IDLE

        # Now a new meeting can start.
        mic2 = ControlledAudioSource()
        remote2 = ControlledAudioSource()
        workflow.start_capture(mic2, remote2, MeetingRemoteSourceKind.SYSTEM)
        assert workflow.state is MeetingWorkflowState.ACTIVE
        workflow.stop_capture()
        workflow.persist()

    def test_start_failure_snapshot_available_for_persistence(
        self, tmp_path: Path
    ) -> None:
        workflow, repo = _make_workflow(tmp_path)
        bad_source = ControlledAudioSource(start_error=RuntimeError("fail"))
        good_source = ControlledAudioSource()

        with pytest.raises(MeetingWorkflowStartError) as exc_info:
            workflow.start_capture(
                bad_source, good_source, MeetingRemoteSourceKind.SYSTEM
            )

        snap = exc_info.value.snapshot
        assert snap.session_id is not None
        assert snap.session_id == workflow.session_id


# ---------------------------------------------------------------------------
# §48 Prepare failure oracle
# ---------------------------------------------------------------------------


class TestPrepareFailure:
    """Prepare failure prevents start, no session active."""

    def test_prepare_failure_no_session_started(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource()

        class BrokenPrepareStorage(MeetingStorage):
            def prepare(self, session_id):
                raise MeetingStorageCollisionError("simulated collision")

        broken_repo = MemoryRepository()
        broken_storage = BrokenPrepareStorage(broken_repo, root=tmp_path)
        broken_workflow = MeetingWorkflow(broken_storage)

        with pytest.raises(MeetingWorkflowError, match="Storage preparation"):
            broken_workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)

        assert broken_workflow.state is MeetingWorkflowState.IDLE
        assert broken_workflow.session_id is None
        assert mic.start_count == 0
        assert remote.start_count == 0

    def test_prepare_failure_same_instance_reusable(self, tmp_path: Path) -> None:
        from buzz.meeting.meeting_storage import MeetingStorageFilesystemError

        class FailOncePrepareStorage(MeetingStorage):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                self._call_count = 0

            def prepare(self, session_id):
                self._call_count += 1
                if self._call_count == 1:
                    raise MeetingStorageFilesystemError("disk full")
                return super().prepare(session_id)

        repo = MemoryRepository()
        storage = FailOncePrepareStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)

        mic = ControlledAudioSource()
        remote = ControlledAudioSource()

        # First attempt fails.
        with pytest.raises(MeetingWorkflowError):
            workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        assert workflow.state is MeetingWorkflowState.IDLE
        assert mic.start_count == 0
        assert remote.start_count == 0

        # Second attempt on SAME workflow succeeds.
        mic2 = ControlledAudioSource()
        remote2 = ControlledAudioSource()
        workflow.start_capture(mic2, remote2, MeetingRemoteSourceKind.SYSTEM)
        assert workflow.state is MeetingWorkflowState.ACTIVE
        assert mic2.start_count == 1
        assert remote2.start_count == 1
        workflow.stop_capture()
        workflow.persist()


# ---------------------------------------------------------------------------
# §49 Stop failure oracle
# ---------------------------------------------------------------------------


class TestStopFailure:
    """Stop failure preserves true state, no false COMPLETED."""

    def test_stop_failure_transitions_to_cleanup_required(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)

        # Inject stop errors on sources to force domain stop failure.
        mic.stop_errors = [RuntimeError("mic cleanup failed")]

        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()

        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED

    def test_stop_failure_preserves_snapshot(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("fail")]

        with pytest.raises(MeetingWorkflowStopError) as exc_info:
            workflow.stop_capture()

        assert exc_info.value.snapshot is not None
        assert exc_info.value.audio is not None
        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED

    def test_stop_failure_does_not_mark_idle(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("fail")]

        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()

        assert workflow.state is not MeetingWorkflowState.IDLE
        assert workflow.is_active

    def test_stop_failure_preserves_partial_result(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("fail")]

        with pytest.raises(MeetingWorkflowStopError) as exc_info:
            workflow.stop_capture()

        # Audio result should still be available.
        assert exc_info.value.audio is not None

    def test_stop_failure_no_completed_claim(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("fail")]

        with pytest.raises(MeetingWorkflowStopError) as exc_info:
            workflow.stop_capture()

        # Must not be COMPLETED.
        assert exc_info.value.snapshot.state is not MeetingSessionState.COMPLETED


# ---------------------------------------------------------------------------
# §50 Cleanup retry oracle
# ---------------------------------------------------------------------------


class TestCleanupRetry:
    """Cleanup retry delegates to MeetingSession.stop()."""

    def test_cleanup_retry_succeeds(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        # Inject a one-time stop failure.
        mic.stop_errors = [RuntimeError("first cleanup fail")]

        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()

        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED

        # Retry — stop_errors is now empty, so this should succeed.
        retry_result = workflow.retry_cleanup()
        assert retry_result.cleanup_succeeded is True
        assert workflow.state is MeetingWorkflowState.AWAITING_PERSISTENCE

    def test_cleanup_retry_then_persist(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("fail")]

        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()

        workflow.retry_cleanup()
        persist = workflow.persist()
        assert workflow.state is MeetingWorkflowState.IDLE
        assert persist.stored_meeting is not None

    def test_cleanup_retry_rejected_when_not_cleanup_required(
        self, tmp_path: Path
    ) -> None:
        workflow, repo = _make_workflow(tmp_path)
        with pytest.raises(MeetingWorkflowStateError, match="Cannot retry cleanup"):
            workflow.retry_cleanup()

    def test_cleanup_retry_still_failing(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        # Inject persistent stop failure.
        mic.stop_errors = [
            RuntimeError("first fail"),
            RuntimeError("second fail"),
        ]

        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()
        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED

        with pytest.raises(MeetingWorkflowStopError):
            workflow.retry_cleanup()
        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED


# ---------------------------------------------------------------------------
# §51 Persistence thread-boundary architecture
# ---------------------------------------------------------------------------


class TestPersistenceBoundary:
    """Capture stop does NOT call MeetingStorage.save()."""

    def test_stop_does_not_call_save(self, tmp_path: Path) -> None:
        save_call_log: list[str] = []

        class TrackingRepository(MemoryRepository):
            def atomic_replace(self, bundle, *, validate_existing):
                save_call_log.append("save")
                super().atomic_replace(bundle, validate_existing=validate_existing)

        repo = TrackingRepository()
        storage = MeetingStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)

        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)

        # Stop capture — save should NOT have been called.
        workflow.stop_capture()
        assert len(save_call_log) == 0

        # Persist — save should be called exactly once.
        workflow.persist()
        assert len(save_call_log) == 1


# ---------------------------------------------------------------------------
# §52 Save-failure oracle
# ---------------------------------------------------------------------------


class TestSaveFailure:
    """Save failure retains pending ownership."""

    def test_save_failure_propagates(self, tmp_path: Path) -> None:
        repo = FailingSaveRepository()
        storage = MeetingStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)

        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)
        workflow.stop_capture()

        with pytest.raises(MeetingWorkflowPersistenceError):
            workflow.persist()

    def test_save_failure_does_not_clear_ownership(self, tmp_path: Path) -> None:
        repo = FailingSaveRepository()
        storage = MeetingStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)

        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)
        workflow.stop_capture()

        with pytest.raises(MeetingWorkflowPersistenceError):
            workflow.persist()

        # Workflow must not be idle — still awaiting persistence.
        assert workflow.state is MeetingWorkflowState.AWAITING_PERSISTENCE
        assert workflow.is_active

    def test_save_retry_can_succeed(self, tmp_path: Path) -> None:
        repo = FailingSaveOnceRepository()
        storage = MeetingStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)

        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)
        workflow.stop_capture()

        # First persist fails.
        with pytest.raises(MeetingWorkflowPersistenceError):
            workflow.persist()

        # Retry succeeds.
        result = workflow.persist()
        assert workflow.state is MeetingWorkflowState.IDLE
        assert result.stored_meeting is not None


# ---------------------------------------------------------------------------
# §53 Foreign-result oracle
# ---------------------------------------------------------------------------


class TestForeignResult:
    """Foreign snapshot persistence is rejected."""

    def test_foreign_session_id_rejected(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        sid = workflow.session_id
        assert sid is not None

        workflow.stop_capture()
        # Verify normal persist works.
        result = workflow.persist()
        assert result.session_id == sid

    def test_workflow_rejects_state_mismatch(self, tmp_path: Path) -> None:
        """Persist when no pending snapshot fails."""
        workflow, repo = _make_workflow(tmp_path)
        with pytest.raises(MeetingWorkflowStateError):
            workflow.persist()


# ---------------------------------------------------------------------------
# §54 No premature ownership clear
# ---------------------------------------------------------------------------


class TestOwnershipRetention:
    """Ownership not cleared on stop/start/save-failure."""

    def test_ownership_retained_after_stop(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        sid = workflow.session_id
        workflow.stop_capture()
        assert workflow.session_id == sid
        assert workflow.is_active

    def test_ownership_retained_after_save_failure(self, tmp_path: Path) -> None:
        repo = FailingSaveRepository()
        storage = MeetingStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)

        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)
        workflow.stop_capture()
        sid = workflow.session_id

        with pytest.raises(MeetingWorkflowPersistenceError):
            workflow.persist()

        assert workflow.session_id == sid
        assert workflow.is_active

    def test_ownership_cleared_after_successful_persist(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        workflow.stop_capture()
        workflow.persist()
        assert workflow.session_id is None
        assert not workflow.is_active

    def test_ownership_retained_after_start_failure(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        bad_source = ControlledAudioSource(start_error=RuntimeError("fail"))
        good_source = ControlledAudioSource()

        with pytest.raises(MeetingWorkflowStartError):
            workflow.start_capture(
                bad_source, good_source, MeetingRemoteSourceKind.SYSTEM
            )

        assert workflow.session_id is not None
        assert workflow.is_active


# ---------------------------------------------------------------------------
# §32 Partial meeting preservation
# ---------------------------------------------------------------------------


class TestPartialMeeting:
    """PARTIAL outcome is not rejected by workflow."""

    def test_partial_outcome_can_be_persisted(self, tmp_path: Path) -> None:
        """When start fails with partial audio, the snapshot is persistable."""
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource(start_error=RuntimeError("remote fail"))

        with pytest.raises(MeetingWorkflowStartError) as exc_info:
            workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)

        # Workflow retains ownership and the snapshot is persistable.
        assert workflow.state is MeetingWorkflowState.AWAITING_PERSISTENCE
        snap = exc_info.value.snapshot
        assert snap.session_id is not None

        persist = workflow.persist()
        assert persist.session_id == snap.session_id


# ---------------------------------------------------------------------------
# §33 Remote-source provenance
# ---------------------------------------------------------------------------


class TestRemoteSourceProvenance:
    """Workflow preserves caller-supplied remote source kind."""

    def test_system_provenance_preserved(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(
            tmp_path,
        )
        snap = workflow.snapshot()
        assert snap is not None
        assert snap.remote_source_kind is MeetingRemoteSourceKind.SYSTEM

    def test_application_provenance_preserved(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.APPLICATION)
        snap = workflow.snapshot()
        assert snap is not None
        assert snap.remote_source_kind is MeetingRemoteSourceKind.APPLICATION
        workflow.stop_capture()
        workflow.persist()


# ---------------------------------------------------------------------------
# §37 Qt guard (behavioral)
# ---------------------------------------------------------------------------


class TestQtGuard:
    """Workflow module is importable without Qt."""

    def test_import_without_qapplication(self) -> None:
        import importlib

        mod = importlib.import_module("buzz.meeting.meeting_workflow")
        assert mod is not None
        assert hasattr(mod, "MeetingWorkflow")
        assert hasattr(mod, "MeetingWorkflowState")


# ---------------------------------------------------------------------------
# §35 / §36 No final transcription / summary / AI
# ---------------------------------------------------------------------------


class TestNoExternalDependencies:
    """Workflow module does not import final transcription, summary, or AI."""

    def test_no_final_transcription_import(self) -> None:
        source_path = (
            pathlib.Path(__file__).resolve().parent.parent.parent
            / "buzz"
            / "meeting"
            / "meeting_workflow.py"
        )
        content = source_path.read_text(encoding="utf-8")
        assert "FinalTranscription" not in content
        assert "MeetingTrackTranscriber" not in content
        assert "MeetingSummary" not in content
        assert "SummaryProvider" not in content
        assert "OpenAICompatible" not in content
        assert "portable_ai" not in content
        assert "meeting_minutes" not in content


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


class TestPersistRejectedWhenNotAwaiting:
    """Persist rejected when workflow is in wrong state."""

    def test_persist_rejected_when_idle(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        with pytest.raises(MeetingWorkflowStateError):
            workflow.persist()

    def test_persist_rejected_when_active(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        with pytest.raises(MeetingWorkflowStateError):
            workflow.persist()
        workflow.stop_capture()
        workflow.persist()

    def test_persist_rejected_when_starting(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource(pause_start=True)
        remote = ControlledAudioSource(pause_start=True)

        started = threading.Event()

        def do_start():
            try:
                workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
            except Exception:
                pass
            finally:
                started.set()

        t = threading.Thread(target=do_start)
        t.start()
        mic.start_entered.wait(timeout=5)
        assert workflow.state is MeetingWorkflowState.STARTING

        with pytest.raises(MeetingWorkflowStateError):
            workflow.persist()

        mic.allow_start.set()
        remote.allow_start.set()
        started.wait(timeout=5)
        t.join(timeout=5)

        # Clean up.
        try:
            workflow.stop_capture()
        except MeetingWorkflowStopError:
            pass
        try:
            workflow.persist()
        except Exception:
            pass


class TestSnapshotAccess:
    """Snapshot access in various states."""

    def test_snapshot_none_when_idle(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        assert workflow.snapshot() is None

    def test_snapshot_available_when_active(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        snap = workflow.snapshot()
        assert snap is not None
        assert snap.session_id == workflow.session_id

    def test_snapshot_available_after_stop(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        workflow.stop_capture()
        snap = workflow.snapshot()
        assert snap is not None
        assert snap.state is MeetingSessionState.COMPLETED

    def test_snapshot_available_after_start_failure(self, tmp_path: Path) -> None:
        workflow, repo = _make_workflow(tmp_path)
        bad = ControlledAudioSource(start_error=RuntimeError("fail"))
        good = ControlledAudioSource()
        with pytest.raises(MeetingWorkflowStartError):
            workflow.start_capture(bad, good, MeetingRemoteSourceKind.SYSTEM)
        snap = workflow.snapshot()
        assert snap is not None
        assert snap.state is MeetingSessionState.FAILED


class TestStopCaptureReturnContract:
    """stop_capture return value contract."""

    def test_stop_returns_snapshot_and_audio(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        result = workflow.stop_capture()
        assert result.snapshot is not None
        assert result.audio is not None
        assert result.cleanup_succeeded is True

    def test_stop_audio_has_meeting_result(self, tmp_path: Path) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        result = workflow.stop_capture()
        assert result.audio is not None
        assert result.audio.microphone is not None
        assert result.audio.remote is not None
        assert result.audio.outcome in (
            MeetingAudioTracksOutcome.COMPLETE,
            MeetingAudioTracksOutcome.PARTIAL,
        )


class TestMeetingRemoteSourceKindValues:
    """Both SYSTEM and APPLICATION work as remote source kinds."""

    @pytest.mark.parametrize(
        "kind",
        [
            MeetingRemoteSourceKind.SYSTEM,
            MeetingRemoteSourceKind.APPLICATION,
        ],
    )
    def test_remote_source_kind(self, tmp_path: Path, kind) -> None:
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        result = workflow.start_capture(mic, remote, kind)
        assert result.snapshot.remote_source_kind is kind
        workflow.stop_capture()
        workflow.persist()


# ---------------------------------------------------------------------------
# Concurrent persist oracle (F2)
# ---------------------------------------------------------------------------


class TestConcurrentPersist:
    """Concurrent persist calls must not duplicate repository saves."""

    def test_second_persist_rejected_when_first_in_progress(
        self, tmp_path: Path
    ) -> None:
        repo = BlockingSaveRepository()
        storage = MeetingStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)

        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)
        workflow.stop_capture()

        # Start persist in background — it will block in repository.
        persist_errors: list[Exception] = []
        persist_done = threading.Event()

        def do_persist_a():
            try:
                workflow.persist()
            except Exception as exc:
                persist_errors.append(exc)
            finally:
                persist_done.set()

        t_a = threading.Thread(target=do_persist_a)
        t_a.start()
        repo.save_entered.wait(timeout=5)

        # Second persist must be rejected immediately.
        with pytest.raises(MeetingWorkflowPersistenceInProgressError):
            workflow.persist()

        # Release the first persist.
        repo.allow_save.set()
        persist_done.wait(timeout=5)
        t_a.join(timeout=5)

        assert not persist_errors
        assert workflow.state is MeetingWorkflowState.IDLE

    def test_save_failure_clears_persisting_guard(self, tmp_path: Path) -> None:
        repo = FailingSaveRepository()
        storage = MeetingStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)

        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)
        workflow.stop_capture()

        # First persist fails.
        with pytest.raises(MeetingWorkflowPersistenceError):
            workflow.persist()

        # Guard is cleared — second persist can proceed (and fail again).
        with pytest.raises(MeetingWorkflowPersistenceError):
            workflow.persist()

        # Ownership still retained.
        assert workflow.state is MeetingWorkflowState.AWAITING_PERSISTENCE
        assert workflow.is_active


# ---------------------------------------------------------------------------
# CLEANUP_REQUIRED persistence (F7)
# ---------------------------------------------------------------------------


class TestCleanupRequiredPersistence:
    """Emergency persistence in CLEANUP_REQUIRED retains ownership."""

    def test_persist_during_cleanup_required_retains_ownership(
        self, tmp_path: Path
    ) -> None:
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("mic stop failed")]

        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()

        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED
        sid = workflow.session_id
        assert sid is not None

        # Persist the nonterminal snapshot.
        result = workflow.persist()
        assert result.session_id == sid

        # Ownership retained — state still CLEANUP_REQUIRED.
        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED
        assert workflow.session_id == sid
        assert workflow.is_active

    def test_retry_cleanup_after_emergency_persist(self, tmp_path: Path) -> None:
        """Full lifecycle: stop fail → emergency persist → retry → persist."""
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("mic stop failed")]

        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()

        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED

        # Emergency persist of nonterminal snapshot.
        result1 = workflow.persist()
        sid = result1.session_id

        # Retry cleanup — succeeds now.
        retry_result = workflow.retry_cleanup()
        assert retry_result.cleanup_succeeded is True
        assert workflow.state is MeetingWorkflowState.AWAITING_PERSISTENCE

        # Persist the final COMPLETED snapshot.
        result2 = workflow.persist()
        assert result2.session_id == sid
        assert result2.stored_meeting.state is MeetingSessionState.COMPLETED

        # Now ownership is released.
        assert workflow.state is MeetingWorkflowState.IDLE
        assert not workflow.is_active

    def test_same_snapshot_persisted_twice_is_noop(self, tmp_path: Path) -> None:
        save_count = 0

        class CountingRepository(MemoryRepository):
            def atomic_replace(self, bundle, *, validate_existing):
                nonlocal save_count
                save_count += 1
                super().atomic_replace(bundle, validate_existing=validate_existing)

        repo = CountingRepository()
        storage = MeetingStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)

        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)

        mic.stop_errors = [RuntimeError("fail")]
        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()

        # First persist saves.
        workflow.persist()
        assert save_count == 1

        # Second persist of same snapshot is a no-op.
        workflow.persist()
        assert save_count == 1
        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED

    def test_retry_cleanup_clears_persisted_marker(self, tmp_path: Path) -> None:
        save_count = 0

        class CountingRepository(MemoryRepository):
            def atomic_replace(self, bundle, *, validate_existing):
                nonlocal save_count
                save_count += 1
                super().atomic_replace(bundle, validate_existing=validate_existing)

        repo = CountingRepository()
        storage = MeetingStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)

        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)

        mic.stop_errors = [RuntimeError("fail")]
        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()

        # Emergency persist.
        workflow.persist()
        assert save_count == 1

        # Retry cleanup produces new snapshot.
        workflow.retry_cleanup()
        assert workflow.state is MeetingWorkflowState.AWAITING_PERSISTENCE

        # Persist new snapshot — must actually save again.
        workflow.persist()
        assert save_count == 2


# ---------------------------------------------------------------------------
# Start-failure cleanup classification
# ---------------------------------------------------------------------------


class TestStartFailureCleanupClassification:
    """Start failure classifies cleanup from domain state."""

    def test_cleanup_complete_goes_to_awaiting_persistence(
        self, tmp_path: Path
    ) -> None:
        """When tracks layer completes cleanup, state is AWAITING_PERSISTENCE."""
        workflow, repo = _make_workflow(tmp_path)
        # Use sources that fail on start — tracks layer cleans up all sources.
        mic = ControlledAudioSource(start_error=RuntimeError("mic boom"))
        remote = ControlledAudioSource()

        with pytest.raises(MeetingWorkflowStartError):
            workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)

        # Tracks layer cleaned up → STOPPED → AWAITING_PERSISTENCE.
        assert workflow.state is MeetingWorkflowState.AWAITING_PERSISTENCE
        snap = workflow.snapshot()
        assert snap is not None
        assert snap.audio_state is MeetingAudioTracksState.STOPPED
        assert snap.state is MeetingSessionState.FAILED
        assert workflow.session_id is not None

    def test_start_failure_persists_failed_state(self, tmp_path: Path) -> None:
        """Persisted FAILED snapshot preserves exact domain state."""
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource(start_error=RuntimeError("boom"))
        remote = ControlledAudioSource()

        with pytest.raises(MeetingWorkflowStartError) as exc_info:
            workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)

        original_session_id = exc_info.value.snapshot.session_id

        persist = workflow.persist()
        assert persist.session_id == original_session_id
        assert persist.stored_meeting.state is MeetingSessionState.FAILED
        assert persist.stored_meeting.session_id == original_session_id
        assert workflow.state is MeetingWorkflowState.IDLE


# ---------------------------------------------------------------------------
# Mutation oracle tests
# ---------------------------------------------------------------------------


class TestMutationOracles:
    """Mechanically kill key mutations."""

    def test_prepare_skipped(self, tmp_path: Path) -> None:
        """Prepare failure prevents source start."""
        workflow, repo = _make_workflow(tmp_path)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource()

        class BrokenPrepareStorage(MeetingStorage):
            def prepare(self, session_id):
                raise MeetingStorageCollisionError("collision")

        broken = MeetingWorkflow(
            BrokenPrepareStorage(MemoryRepository(), root=tmp_path)
        )
        with pytest.raises(MeetingWorkflowError):
            broken.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        assert mic.start_count == 0
        assert remote.start_count == 0

    def test_double_active_meeting(self, tmp_path: Path) -> None:
        """Second start while active is rejected."""
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic2 = ControlledAudioSource()
        remote2 = ControlledAudioSource()
        with pytest.raises(MeetingWorkflowStateError):
            workflow.start_capture(mic2, remote2, MeetingRemoteSourceKind.SYSTEM)
        assert mic2.start_count == 0

    def test_stop_error_not_swallowed(self, tmp_path: Path) -> None:
        """Stop error is raised, not silently absorbed."""
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("fail")]
        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()

    def test_save_failure_not_swallowed(self, tmp_path: Path) -> None:
        """Save failure is raised, not silently absorbed."""
        repo = FailingSaveRepository()
        storage = MeetingStorage(repo, root=tmp_path)
        workflow = MeetingWorkflow(storage)
        mic = ControlledAudioSource()
        remote = ControlledAudioSource()
        workflow.start_capture(mic, remote, MeetingRemoteSourceKind.SYSTEM)
        mic.start_entered.wait(timeout=5)
        remote.start_entered.wait(timeout=5)
        workflow.stop_capture()
        with pytest.raises(MeetingWorkflowPersistenceError):
            workflow.persist()

    def test_no_stopping_to_completed_coercion(self, tmp_path: Path) -> None:
        """Stop failure does NOT produce COMPLETED state."""
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("fail")]
        with pytest.raises(MeetingWorkflowStopError) as exc_info:
            workflow.stop_capture()
        assert exc_info.value.snapshot.state is not MeetingSessionState.COMPLETED

    def test_second_meeting_during_cleanup_required(self, tmp_path: Path) -> None:
        """Second start rejected during CLEANUP_REQUIRED."""
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("fail")]
        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()
        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED
        mic2 = ControlledAudioSource()
        remote2 = ControlledAudioSource()
        with pytest.raises(MeetingWorkflowStateError):
            workflow.start_capture(mic2, remote2, MeetingRemoteSourceKind.SYSTEM)
        assert mic2.start_count == 0

    def test_cleanup_required_persist_does_not_release_ownership(
        self, tmp_path: Path
    ) -> None:
        """CLEANUP_REQUIRED persist must NOT clear ownership."""
        workflow, mic, remote, repo = _start_and_activate(tmp_path)
        mic.stop_errors = [RuntimeError("fail")]
        with pytest.raises(MeetingWorkflowStopError):
            workflow.stop_capture()
        workflow.persist()
        assert workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED
        assert workflow.is_active
        assert workflow.session_id is not None
