"""Hardware-free meeting slice tests with real workflow, storage and QSql."""

from threading import get_ident
from unittest.mock import Mock

import numpy as np
import pytest
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from buzz.audio_capture.source import AudioSourceError
from buzz.audio_capture.windows_application_targets import WindowsApplicationAudioTarget
from buzz.db.meeting_library_repository import QSqlMeetingLibraryRepository
from buzz.db.meeting_storage_repository import QSqlMeetingRepository
from buzz.db.meeting_transcription_repository import QSqlMeetingTranscriptionRepository
from buzz.meeting.final_transcription import (
    FinalTranscriptionConfig,
    FinalTranscriptionReadService,
    FinalTranscriptionStatus,
    TrackTranscriptionInputSegment,
)
from buzz.meeting.meeting_audio_tracks import MeetingAudioTracksOutcome
from buzz.meeting.meeting_library import MeetingLibraryService
from buzz.meeting.meeting_session import MeetingRemoteSourceKind
from buzz.meeting.meeting_storage import MeetingStorage, MeetingStorageDatabaseError
from buzz.meeting.meeting_workflow import MeetingWorkflow, MeetingWorkflowState
from buzz.widgets.meeting_capture_widget import MeetingCaptureWidget
from buzz.widgets.meeting_final_transcription import MeetingFinalTranscription
from buzz.widgets.meeting_mode import MeetingModeController
from buzz.widgets.meetings_library_widget import MeetingsLibraryWidget
from tests.meeting.meeting_workflow_test import ControlledAudioSource


@pytest.fixture(scope="session")
def qapp_cls():
    return QApplication


@pytest.fixture
def mode(db, tmp_path, qtbot):
    storage = MeetingStorage(QSqlMeetingRepository(db), root=tmp_path / "meetings")
    controller = MeetingModeController(MeetingWorkflow(storage))
    yield controller, storage
    if controller.active:
        controller.end()
        qtbot.waitUntil(lambda: not controller.active, timeout=10000)


def begin(qtbot, controller, kind=MeetingRemoteSourceKind.SYSTEM):
    mic, remote = ControlledAudioSource(), ControlledAudioSource()
    controller.start(mic, remote, kind)
    qtbot.waitUntil(lambda: controller.status == "Recording", timeout=5000)
    mic.deliver(np.ones(3200, dtype=np.float32) * 0.1)
    remote.deliver(np.ones(3200, dtype=np.float32) * 0.2)
    return mic, remote


@pytest.mark.parametrize("kind", list(MeetingRemoteSourceKind))
def test_two_tracks_saved_and_exact_identity_in_library(mode, db, qtbot, kind):
    controller, storage = mode
    library = MeetingsLibraryWidget(
        MeetingLibraryService(QSqlMeetingLibraryRepository(db))
    )
    qtbot.addWidget(library)
    controller.saved.connect(lambda _: library.refresh())
    begin(qtbot, controller, kind)
    session_id = controller.workflow.session_id
    with qtbot.waitSignal(controller.saved, timeout=5000):
        controller.end()
    stored = storage.load(session_id)
    assert stored.remote_source_kind is kind
    assert stored.microphone.path.name == "microphone.wav"
    assert stored.remote.path.name == "remote.wav"
    assert stored.microphone.sample_count == stored.remote.sample_count == 3200
    assert library.table_model.meeting_at(0).session_id == session_id
    assert not controller.active


def test_prepare_before_capture_and_start_stop_off_gui_persist_on_owner(
    mode, qtbot, monkeypatch
):
    controller, storage = mode
    gui = get_ident()
    prepared = []
    original = storage.prepare

    def prepare(session_id):
        assert get_ident() != gui
        result = original(session_id)
        prepared.append(result)
        return result

    monkeypatch.setattr(storage, "prepare", prepare)
    save = storage.save

    def owner_save(snapshot):
        assert get_ident() == gui
        return save(snapshot)

    monkeypatch.setattr(storage, "save", owner_save)
    mic, remote = ControlledAudioSource(pause_start=True), ControlledAudioSource()
    controller.start(mic, remote, MeetingRemoteSourceKind.SYSTEM)
    qtbot.waitUntil(mic.start_entered.is_set, timeout=5000)
    assert prepared
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: bool(ticks))
    with pytest.raises(RuntimeError):
        controller.start(
            ControlledAudioSource(),
            ControlledAudioSource(),
            MeetingRemoteSourceKind.SYSTEM,
        )
    mic.allow_start.set()
    qtbot.waitUntil(lambda: controller.status == "Recording")
    mic.pause_stop = True
    controller.end()
    qtbot.waitUntil(mic.stop_entered.is_set)
    QTimer.singleShot(0, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: len(ticks) == 2)
    mic.allow_stop.set()
    qtbot.waitUntil(lambda: not controller.active)


def test_remote_failure_preserves_true_partial(mode, qtbot):
    controller, storage = mode
    mic, remote = begin(qtbot, controller)
    remote.fail(AudioSourceError("remote lost"))
    qtbot.waitUntil(lambda: "degraded" in controller.status)
    mic.deliver(np.ones(1600, dtype=np.float32) * 0.1)
    controller.end()
    qtbot.waitUntil(lambda: not controller.active)
    stored = storage.load(controller.saved_id)
    assert stored.audio_outcome is MeetingAudioTracksOutcome.PARTIAL
    assert stored.microphone.sample_count == 4800
    assert "partial" in controller.status


def test_save_failure_retains_ownership_and_retry(mode, qtbot, monkeypatch):
    from types import SimpleNamespace

    from buzz.widgets.main_window import MainWindow

    controller, storage = mode
    begin(qtbot, controller)
    original = storage.save
    monkeypatch.setattr(
        storage, "save", Mock(side_effect=MeetingStorageDatabaseError("disk"))
    )
    saved = Mock()
    opened = Mock()
    transcription = Mock()
    controller.saved.connect(saved)
    owner = SimpleNamespace(
        meetings_library_widget=Mock(),
        meeting_controller=controller,
        meeting_final=transcription,
        meeting_capture_widget=SimpleNamespace(config=FinalTranscriptionConfig()),
        on_meeting_open_requested=opened,
        _meeting_close_pending=False,
    )
    controller.saved.connect(lambda result: MainWindow._meeting_saved(owner, result))
    controller.end()
    qtbot.waitUntil(lambda: "Save failed" in controller.status)
    assert controller.active and controller.saved_id is None
    saved.assert_not_called()
    opened.assert_not_called()
    transcription.request.assert_not_called()
    with pytest.raises(RuntimeError):
        controller.start(
            ControlledAudioSource(),
            ControlledAudioSource(),
            MeetingRemoteSourceKind.SYSTEM,
        )
    monkeypatch.setattr(storage, "save", original)
    controller.end()
    assert not controller.active
    saved.assert_called_once()


def test_cleanup_required_blocks_second_meeting_after_emergency_save(mode, qtbot):
    controller, _ = mode
    mic, _ = begin(qtbot, controller)
    mic.stop_errors = [RuntimeError("stop failed")]
    controller.end()
    qtbot.waitUntil(lambda: controller.saved_id is not None)
    assert controller.workflow.state is MeetingWorkflowState.CLEANUP_REQUIRED
    assert controller.active
    with pytest.raises(RuntimeError):
        controller.start(
            ControlledAudioSource(),
            ControlledAudioSource(),
            MeetingRemoteSourceKind.SYSTEM,
        )
    controller.end()
    qtbot.waitUntil(lambda: not controller.active)


@pytest.fixture
def capture(mode, qtbot, monkeypatch):
    monkeypatch.setattr(
        "buzz.widgets.audio_devices_combo_box.AudioDevicesComboBox.get_audio_devices",
        lambda self: [(7, "Test mic")],
    )
    monkeypatch.setattr(
        "buzz.widgets.audio_devices_combo_box.AudioDevicesComboBox.get_default_device_id",
        lambda self: 7,
    )
    widget = MeetingCaptureWidget(mode[0])
    qtbot.addWidget(widget)
    return widget


def test_window_close_cancel_then_confirm_waits_for_save(
    capture, mode, qtbot, monkeypatch
):
    controller, _ = mode
    mic, _ = begin(qtbot, controller)
    capture.show()
    monkeypatch.setattr(capture, "confirm_end", lambda: False)
    assert not capture.close()
    assert controller.active
    assert not mic.stop_entered.is_set()
    mic.pause_stop = True
    monkeypatch.setattr(capture, "confirm_end", lambda: True)
    assert not capture.close()
    qtbot.waitUntil(mic.stop_entered.is_set)
    assert capture.isVisible() and controller.active
    mic.allow_stop.set()
    qtbot.waitUntil(lambda: not capture.isVisible())
    assert controller.saved_id is not None


def test_duplicate_stop_persists_once(mode, qtbot, monkeypatch):
    controller, storage = mode
    mic, remote = begin(qtbot, controller)
    save = Mock(wraps=storage.save)
    monkeypatch.setattr(storage, "save", save)
    mic.pause_stop = True

    controller.end()
    qtbot.waitUntil(mic.stop_entered.is_set)
    controller.end()
    mic.allow_stop.set()
    qtbot.waitUntil(lambda: not controller.active)

    assert mic.stop_count == remote.stop_count == 1
    save.assert_called_once()


def test_close_while_starting_defers_stop_until_capture_worker_returns(
    capture, mode, qtbot, monkeypatch
):
    controller, _ = mode
    mic, remote = ControlledAudioSource(pause_start=True), ControlledAudioSource()
    controller.start(mic, remote, MeetingRemoteSourceKind.SYSTEM)
    qtbot.waitUntil(mic.start_entered.is_set)
    capture.show()
    monkeypatch.setattr(capture, "confirm_end", lambda: True)
    assert not capture.close()
    assert not mic.stop_entered.is_set()
    mic.allow_start.set()
    qtbot.waitUntil(lambda: not controller.active)
    assert mic.stop_entered.is_set()
    assert controller.saved_id is not None
    assert not capture.isVisible()


@pytest.mark.parametrize("kind", list(MeetingRemoteSourceKind))
def test_capture_controls_build_selected_sources(
    capture, mode, qtbot, monkeypatch, kind
):
    mic, remote = ControlledAudioSource(), ControlledAudioSource()
    microphone_factory = Mock(return_value=mic)
    system_factory = Mock(return_value=remote)
    application_factory = Mock(return_value=remote)
    prefix = "buzz.widgets.meeting_capture_widget."
    monkeypatch.setattr(prefix + "SoundDeviceAudioSource", microphone_factory)
    monkeypatch.setattr(prefix + "WindowsSystemAudioSource", system_factory)
    monkeypatch.setattr(prefix + "WindowsProcessAudioSource", application_factory)
    target = WindowsApplicationAudioTarget(
        1, "Meeting", 2, 3, "meeting.exe", None, None
    )
    monkeypatch.setattr(
        prefix + "list_windows_application_audio_targets", lambda: [target]
    )
    validate = Mock(return_value=True)
    monkeypatch.setattr(prefix + "validate_windows_application_audio_target", validate)
    if kind is MeetingRemoteSourceKind.APPLICATION:
        capture.remote.setCurrentIndex(1)
        capture.target.setCurrentIndex(1)
    capture.start_button.click()
    qtbot.waitUntil(lambda: mode[0].status == "Recording")
    try:
        microphone_factory.assert_called_once_with(7, 16000)
        if kind is MeetingRemoteSourceKind.APPLICATION:
            validate.assert_called_once_with(target)
            application_factory.assert_called_once_with(process_id=3)
            system_factory.assert_not_called()
        else:
            system_factory.assert_called_once_with()
            application_factory.assert_not_called()
    finally:
        capture.stop_button.click()
        qtbot.waitUntil(lambda: not mode[0].active)


def test_main_window_close_waits_for_save_and_preserves_workflow(
    mode, db, qtbot, monkeypatch
):
    from buzz.widgets.main_window import MainWindow
    from buzz.db.service.transcription_service import TranscriptionService

    controller, _ = mode
    monkeypatch.setattr(
        "buzz.widgets.main_window.PluginManager.initialize", lambda self: None
    )
    final = ClosingFinal()
    final.allow_close = True
    window = MainWindow(
        Mock(spec=TranscriptionService),
        Mock(),
        Mock(),
        Mock(),
        Mock(),
        controller,
        final,
    )
    qtbot.addWidget(window)
    # Avoid hardware discovery; the capture close contract is tested separately.
    capture = Mock()
    capture.confirm_end.return_value = False
    window.meeting_capture_widget = capture
    detail = Mock()
    window.meeting_detail_widget = detail
    begin(qtbot, controller)
    window.show()
    assert not window.close()
    assert controller.active
    assert final.close_calls == 0
    final.request.assert_not_called()
    capture.confirm_end.return_value = True
    assert not window.close()
    assert final.close_calls == 1
    qtbot.waitUntil(lambda: not controller.active)
    qtbot.waitUntil(lambda: not window.isVisible())
    assert controller.saved_id is not None
    detail.open_meeting.assert_called_once_with(controller.saved_id)
    final.request.assert_not_called()


def test_main_window_save_dispatch_uses_durable_id(mode, qtbot):
    from buzz.widgets.main_window import MainWindow
    from types import SimpleNamespace

    controller, storage = mode
    final = Mock()
    final.request.side_effect = lambda sid, config: storage.load(sid) or pytest.fail(
        "not saved"
    )
    order = []
    library = Mock()
    library.refresh.side_effect = lambda: order.append("refresh")
    open_meeting = Mock(
        side_effect=lambda meeting_id: order.append(("open", meeting_id))
    )
    owner = SimpleNamespace(
        meetings_library_widget=library,
        meeting_controller=controller,
        meeting_final=final,
        meeting_capture_widget=SimpleNamespace(config=FinalTranscriptionConfig()),
        on_meeting_open_requested=open_meeting,
        _meeting_close_pending=False,
    )
    controller.saved.connect(lambda result: MainWindow._meeting_saved(owner, result))
    begin(qtbot, controller)
    final.request.assert_not_called()
    controller.end()
    qtbot.waitUntil(lambda: not controller.active)
    final.request.assert_called_once_with(
        controller.saved_id, owner.meeting_capture_widget.config
    )
    library.refresh.assert_called_once()
    open_meeting.assert_called_once_with(controller.saved_id)
    assert order == ["refresh", ("open", controller.saved_id)]


def test_application_quit_respects_rejected_window_close():
    from types import SimpleNamespace
    from PyQt6.QtCore import QEvent
    from buzz.widgets.application import Application

    window = Mock()
    window.close.return_value = False
    assert Application.event(SimpleNamespace(window=window), QEvent(QEvent.Type.Quit))
    window.close.assert_called_once()


class Adapter(QObject):
    track_completed = pyqtSignal(list)
    track_rich_completed = pyqtSignal(object)
    track_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.calls = []
        self.shutdown_results = []
        self.shutdown_calls = []

    def start(self, path, rate, config):
        self.calls.append((path, rate, config, get_ident()))

    def shutdown(self, timeout_ms=10000):
        self.shutdown_calls.append(timeout_ms)
        return self.shutdown_results.pop(0) if self.shutdown_results else True


class ClosingFinal(QObject):
    changed = pyqtSignal()
    idle = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.pending = 0
        self.allow_close = False
        self.close_calls = 0
        self.request = Mock()

    def close(self):
        self.close_calls += 1
        return self.allow_close


def test_main_window_retains_ownership_until_final_shutdown_is_safe(qtbot, monkeypatch):
    from buzz.widgets.main_window import MainWindow
    from buzz.db.service.transcription_service import TranscriptionService

    monkeypatch.setattr(
        "buzz.widgets.main_window.PluginManager.initialize", lambda self: None
    )
    final = ClosingFinal()
    window = MainWindow(
        Mock(spec=TranscriptionService),
        Mock(),
        Mock(),
        Mock(),
        Mock(),
        meeting_final=final,
    )
    qtbot.addWidget(window)
    window.show()

    assert not window.close()
    assert window.isVisible()
    assert final.parent() is window
    assert final.close_calls == 1
    final.allow_close = True
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=5000)
    assert final.close_calls >= 2


def test_final_close_honors_false_and_permanently_rejects_submissions(mode, db):
    _, storage = mode
    adapter = Adapter()
    adapter.shutdown_results = [False, True]
    final = MeetingFinalTranscription(
        storage, QSqlMeetingTranscriptionRepository(db), adapter
    )

    assert not final.close()
    with pytest.raises(RuntimeError, match="closed"):
        final.request("never-started", FinalTranscriptionConfig())
    adapter.track_completed.emit([])
    adapter.track_error.emit("late")
    assert final.pending == 0
    assert final.close()
    assert adapter.shutdown_calls == [0, 0]


def test_final_close_retries_owned_asr_and_ignores_late_callbacks(mode, db, qtbot):
    controller, storage = mode
    begin(qtbot, controller)
    controller.end()
    qtbot.waitUntil(lambda: not controller.active)
    adapter = Adapter()
    final = MeetingFinalTranscription(
        storage, QSqlMeetingTranscriptionRepository(db), adapter
    )
    final.request(controller.saved_id, FinalTranscriptionConfig())
    qtbot.waitUntil(lambda: len(adapter.calls) == 1)
    adapter.shutdown_results = [False, True]

    assert not final.close()
    assert final.pending == 1
    adapter.track_completed.emit([TrackTranscriptionInputSegment(0, 100, "late")])
    adapter.track_error.emit("late")
    assert final.pending == 1
    assert not final.close()
    qtbot.waitUntil(lambda: final.pending == 0)
    assert len(adapter.calls) == 1
    assert final.close()
    assert adapter.shutdown_calls == [0, 0, 0]


def test_second_saved_meeting_is_queued_while_first_asr_is_pending(mode, db, qtbot):
    controller, storage = mode
    repository = QSqlMeetingTranscriptionRepository(db)
    reader = FinalTranscriptionReadService(repository)
    adapter = Adapter()
    final = MeetingFinalTranscription(storage, repository, adapter)
    controller.saved.connect(
        lambda result: final.request(result.session_id, FinalTranscriptionConfig())
    )
    begin(qtbot, controller)
    controller.end()
    qtbot.waitUntil(lambda: len(adapter.calls) == 1)
    first_id = controller.saved_id
    begin(qtbot, controller)
    controller.end()
    qtbot.waitUntil(lambda: not controller.active)
    second_id = controller.saved_id
    assert second_id != first_id
    qtbot.waitUntil(
        lambda: reader.load_generation_for_meeting(second_id, 1) is not None
    )
    assert (
        reader.load_generation_for_meeting(second_id, 1).status
        is FinalTranscriptionStatus.QUEUED
    )
    assert len(adapter.calls) == 1
    for count in range(1, 5):
        qtbot.waitUntil(lambda: len(adapter.calls) == count)
        adapter.track_completed.emit([TrackTranscriptionInputSegment(0, 100, "done")])
    qtbot.waitUntil(lambda: not final.pending)
    assert (
        reader.load_generation_for_meeting(first_id, 1).status
        is FinalTranscriptionStatus.COMPLETED
    )
    assert (
        reader.load_generation_for_meeting(second_id, 1).status
        is FinalTranscriptionStatus.COMPLETED
    )
    assert final.close()


def test_final_after_save_failure_preserves_audio_and_retry_contract(mode, db, qtbot):
    controller, storage = mode
    repository = QSqlMeetingTranscriptionRepository(db)
    reader = FinalTranscriptionReadService(repository)
    adapter = Adapter()
    final = MeetingFinalTranscription(storage, repository, adapter)
    config = FinalTranscriptionConfig()

    def saved(result):
        assert storage.load(result.session_id) is not None
        final.request(result.session_id, config)

    controller.saved.connect(saved)
    begin(qtbot, controller)
    assert not adapter.calls
    controller.end()
    qtbot.waitUntil(lambda: len(adapter.calls) == 1)
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: bool(ticks))
    meeting_id = controller.saved_id
    before = storage.load(meeting_id)
    audio = before.microphone.path.read_bytes()
    gen = reader.load_generation_for_meeting(meeting_id, 1)
    assert gen.status is FinalTranscriptionStatus.IN_PROGRESS
    assert adapter.calls[0][3] == get_ident()
    adapter.track_completed.emit([TrackTranscriptionInputSegment(0, 100, "hello")])
    qtbot.waitUntil(lambda: len(adapter.calls) == 2)
    adapter.track_error.emit("inference failed")
    qtbot.waitUntil(lambda: not final.pending)
    gen = reader.load_generation_for_meeting(meeting_id, 1)
    assert gen.status is FinalTranscriptionStatus.PARTIAL
    assert storage.load(meeting_id) == before
    assert before.microphone.path.read_bytes() == audio
    final.retry(gen.generation_id)
    qtbot.waitUntil(lambda: len(adapter.calls) == 3)
    assert adapter.calls[-1][0] == str(before.remote.path)
    adapter.track_completed.emit([TrackTranscriptionInputSegment(0, 100, "remote")])
    qtbot.waitUntil(lambda: not final.pending)
    completed = reader.load_generation_for_meeting(meeting_id, 1)
    assert completed.generation_id == gen.generation_id
    assert completed.status is FinalTranscriptionStatus.COMPLETED
    assert reader.load_transcript(gen.generation_id).segments[0].text == "hello"
    assert final.close()
