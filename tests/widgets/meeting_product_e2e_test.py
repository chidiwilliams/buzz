"""Product regression: real capture ownership, QSql, orchestration and exports.

Only audio hardware, ASR execution, AI execution and dialogs are substituted.
The legacy (non-meeting) transcription service is unused in these scenarios.
"""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from buzz.audio_capture.source import AudioSourceError
from buzz.db.meeting_library_repository import QSqlMeetingLibraryRepository
from buzz.db.meeting_speaker_repository import QSqlMeetingSpeakerRepository
from buzz.db.meeting_storage_repository import QSqlMeetingRepository
from buzz.db.meeting_summary_repository import QSqlMeetingSummaryRepository
from buzz.db.meeting_transcription_repository import QSqlMeetingTranscriptionRepository
from buzz.db.service.transcription_service import TranscriptionService
from buzz.meeting.final_transcription import (
    FinalTranscriptionConfig,
    FinalTranscriptionReadService,
    FinalTranscriptionStatus,
    TrackTranscriptionInputSegment,
)
from buzz.meeting.meeting_audio_tracks import MeetingAudioTracksOutcome
from buzz.meeting.meeting_detail import MeetingDetailService
from buzz.meeting.meeting_library import MeetingLibraryService
from buzz.meeting.meeting_notes import MeetingNotesService, NotesError
from buzz.meeting.meeting_session import MeetingSessionState
from buzz.meeting.meeting_storage import MeetingStorage
from buzz.meeting.meeting_summary import (
    MeetingSummaryFreshness,
    meeting_summary_to_json,
)
from buzz.meeting.meeting_workflow import MeetingWorkflow
from buzz.meeting.speaker_review import MeetingSpeakerReviewService
from buzz.widgets.main_window import MainWindow
from buzz.widgets.meeting_final_transcription import MeetingFinalTranscription
from buzz.widgets.meeting_mode import MeetingModeController
from buzz.widgets.meeting_notes_controller import MeetingNotesController
from tests.meeting.meeting_workflow_test import ControlledAudioSource
from tests.widgets.meeting_mode_test import Adapter
from tests.widgets.meeting_notes_test import ControlledProvider, config


@pytest.fixture(scope="session")
def qapp_cls():
    return QApplication


@pytest.fixture
def product(db, tmp_path, qtbot, monkeypatch):
    storage = MeetingStorage(QSqlMeetingRepository(db), root=tmp_path / "meetings")
    repository = QSqlMeetingTranscriptionRepository(db)
    reader = FinalTranscriptionReadService(repository)
    reviews = MeetingSpeakerReviewService(QSqlMeetingSpeakerRepository(db), reader)
    detail = MeetingDetailService(storage, reader, reviews)
    summaries = QSqlMeetingSummaryRepository(db)
    provider = ControlledProvider()
    requests = []
    summarize = provider.summarize

    def record_request(request):
        requests.append(request)
        return summarize(request)

    provider.summarize = record_request
    notes = MeetingNotesController(
        MeetingNotesService(detail, summaries), provider_factory=lambda _: provider
    )
    capture = MeetingModeController(MeetingWorkflow(storage))
    adapter = Adapter()
    final = MeetingFinalTranscription(storage, repository, adapter)
    mic, remote = ControlledAudioSource(), ControlledAudioSource()
    monkeypatch.setattr(
        "buzz.widgets.audio_devices_combo_box.AudioDevicesComboBox.get_audio_devices",
        lambda _: [(7, "Synthetic microphone")],
    )
    monkeypatch.setattr(
        "buzz.widgets.audio_devices_combo_box.AudioDevicesComboBox.get_default_device_id",
        lambda _: 7,
    )
    monkeypatch.setattr(
        "buzz.widgets.meeting_capture_widget.SoundDeviceAudioSource", lambda *a: mic
    )
    monkeypatch.setattr(
        "buzz.widgets.meeting_capture_widget.WindowsSystemAudioSource", lambda: remote
    )
    monkeypatch.setattr(
        "buzz.widgets.main_window.PluginManager.initialize", lambda _: None
    )
    window = MainWindow(
        Mock(spec=TranscriptionService),
        MeetingLibraryService(QSqlMeetingLibraryRepository(db)),
        detail,
        reviews,
        Mock(),
        meeting_controller=capture,
        meeting_final=final,
        meeting_notes=notes,
    )
    window.new_meeting_action.trigger()
    assert window.meeting_capture_widget.windowTitle() == "New Meeting"
    qtbot.addWidget(window)
    result = SimpleNamespace(
        storage=storage,
        reader=reader,
        summaries=summaries,
        detail=detail,
        notes=notes,
        capture=capture,
        adapter=adapter,
        mic=mic,
        remote=remote,
        final=final,
        provider=provider,
        requests=requests,
        window=window,
        db=db,
        root=tmp_path,
    )
    yield result
    provider.allow_result.set()
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not notes.busy, timeout=15000)
    if capture.active:
        capture.end()
        qtbot.waitUntil(lambda: not capture.active)
    # Release controlled external work even when a mutation trips an oracle
    # before the scenario reaches its normal completion step.
    while final.pending:
        qtbot.waitUntil(lambda: final._asr_call is not None or not final.pending)
        if final._asr_call is not None:
            adapter.track_error.emit("fixture cleanup")
    final.close()
    window.meeting_capture_widget.close()
    window.close()


def record(product, qtbot, *, degraded=False):
    p = product
    before = len(p.adapter.calls)
    mic, remote = p.mic, p.remote
    p.window.meeting_capture_widget.start_button.click()
    qtbot.waitUntil(lambda: p.capture.status == "Recording")
    mic.deliver(np.ones(3200, dtype=np.float32) * 0.1)
    remote.deliver(np.ones(3200, dtype=np.float32) * 0.2)
    identity = p.capture.workflow.session_id
    assert not p.requests, "AI started before explicit request"
    assert len(p.adapter.calls) == before, "ASR started before stop/save"
    if degraded:
        remote.fail(AudioSourceError("remote disappeared"))
        qtbot.waitUntil(lambda: "degraded" in p.capture.status)
        mic.deliver(np.ones(1600, dtype=np.float32) * 0.1)
    p.window.meeting_capture_widget.stop_button.click()
    qtbot.waitUntil(lambda: not p.capture.active)
    assert p.capture.saved_id == identity, "saved meeting identity changed"
    stored = p.storage.load(identity)
    assert stored is not None, "meeting persistence skipped"
    assert stored.state is MeetingSessionState.COMPLETED
    assert mic.stop_entered.is_set() and remote.stop_entered.is_set()
    assert not p.requests, "stop implicitly triggered AI"
    assert p.window.meeting_detail_widget is not None
    for track, count in (
        (stored.microphone, 4800 if degraded else 3200),
        (stored.remote, 3200),
    ):
        assert track.sample_count == count
        audio = sf.info(track.path)
        assert audio.frames == count
        assert audio.samplerate == track.sample_rate
        pcm, _ = sf.read(track.path, dtype="float32")
        expected = 0.1 if track == stored.microphone else 0.2
        np.testing.assert_allclose(pcm, expected, atol=0.0001)
    return identity, stored


def transcribe(product, qtbot, *, fail=False, start=0):
    p = product
    for index in range(start + 1, start + 3):
        qtbot.waitUntil(lambda: len(p.adapter.calls) == index)
        path = Path(p.adapter.calls[-1][0])
        assert path.is_file(), "ASR received non-durable audio"
        if fail:
            p.adapter.track_error.emit("controlled model failure")
        else:
            p.adapter.track_completed.emit(
                [TrackTranscriptionInputSegment(0, 100, f"Plan from {path.stem}.")]
            )
    qtbot.waitUntil(lambda: not p.final.pending)


def authoritative(product, identity):
    snapshot = product.detail.load(identity)
    assert snapshot.meeting.session_id == identity
    assert snapshot.final_generation.meeting_id == identity
    assert snapshot.transcript is not None, "authoritative transcript unavailable"
    assert snapshot.transcript.meeting_id == identity, "wrong transcript meeting"
    assert snapshot.transcript.generation_id == snapshot.final_generation.generation_id
    assert snapshot.final_generation.status is FinalTranscriptionStatus.COMPLETED
    return snapshot


def manual(product, identity, text):
    rendered = product.notes.copy_request(identity)
    snapshot = authoritative(product, identity)
    for segment in snapshot.transcript.segments:
        assert segment.text in rendered
    value = replace(product.provider.result, summary=text)
    artifact = product.notes.import_response(identity, meeting_summary_to_json(value))
    assert artifact.meeting_id == identity, "manual context identity changed"
    assert artifact.source_generation_id == snapshot.final_generation.generation_id
    assert product.summaries.load(artifact.summary_id) == artifact
    return artifact


def test_product_happy_path_selected_persisted_minutes(product, qtbot, monkeypatch):
    p = product
    identity, stored = record(p, qtbot)
    transcribe(p, qtbot)
    source = authoritative(p, identity)
    p.notes.submit(identity, config())
    qtbot.waitUntil(p.provider.entered.is_set)
    assert p.requests == [p.notes.prepare(identity).request]
    assert [e.text for e in p.requests[0].transcript] == [
        s.text for s in source.transcript.segments
    ]
    p.provider.allow_result.set()
    p.provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not p.notes.busy)
    history = p.summaries.list_for_meeting(identity)
    assert len(history) == 1, "API result not persisted for originating meeting"
    (first,) = history
    assert first.source_generation_id == source.final_generation.generation_id
    assert first.source_profile_version == source.final_generation.profile_version
    assert first.source_review_id is None and first.source_review_revision is None
    assert first.meeting_id == identity
    second = manual(p, identity, "SECOND NOTES MUST NOT BE EXPORTED")
    assert {a.summary_id for a in p.notes.history(identity)} == {
        first.summary_id,
        second.summary_id,
    }, "summary history overwritten"
    # Reload through new adapters: no controller cache can stand in for storage.
    assert QSqlMeetingSummaryRepository(p.db).load(first.summary_id) == first
    reloaded = MeetingStorage(QSqlMeetingRepository(p.db), root=p.root / "meetings")
    assert reloaded.load(identity) == stored
    assert authoritative(p, identity) == source
    panel = p.window.meeting_detail_widget.notes_panel
    panel.refresh()
    assert (
        panel.history.currentData() == panel.selected_id
    ), "persisted selection missing from history UI"
    panel.history.setCurrentIndex(
        next(
            i
            for i in range(panel.history.count())
            if panel.history.itemData(i) == first.summary_id
        )
    )
    assert panel.selected_id == first.summary_id
    panel.refresh()
    assert panel.history.currentData() == first.summary_id
    destination = p.root / "selected.md"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(destination), "Markdown (*.md)"),
    )
    panel.export()
    exported = destination.read_bytes()
    assert first.summary.summary.encode() in exported, "selected artifact not exported"
    assert second.summary.summary.encode() not in exported, "latest replaced selection"
    p.notes.export(identity, first.summary_id, p.root / "again.md")
    assert (p.root / "again.md").read_bytes() == exported


def test_product_remote_degradation_preserves_microphone(product, qtbot):
    identity, stored = record(product, qtbot, degraded=True)
    assert stored.audio_outcome is MeetingAudioTracksOutcome.PARTIAL, "PARTIAL coerced"
    assert stored.microphone.sample_count == 4800
    assert "partial" in product.capture.status
    # Drain eligible tracks without assuming damaged remote audio is eligible.
    handled = 0
    while product.final.pending:
        qtbot.waitUntil(
            lambda: len(product.adapter.calls) > handled or not product.final.pending
        )
        if len(product.adapter.calls) > handled:
            handled += 1
            product.adapter.track_completed.emit(
                [TrackTranscriptionInputSegment(0, 100, "usable")]
            )
    assert product.storage.load(identity) == stored


def test_product_final_failure_explicit_retry_same_generation(product, qtbot):
    p = product
    identity, stored = record(p, qtbot)
    transcribe(p, qtbot, fail=True)
    failed = p.reader.load_generation_for_meeting(identity, 1)
    assert failed.status is FinalTranscriptionStatus.FAILED
    assert p.storage.load(identity) == stored
    with pytest.raises(NotesError):
        p.notes.prepare(identity)
    assert len(p.adapter.calls) == 2
    p.final.retry(failed.generation_id)
    transcribe(p, qtbot, start=2)
    source = authoritative(p, identity)
    assert (
        source.final_generation.generation_id == failed.generation_id
    ), "retry generation changed"
    assert p.storage.load(identity) == stored


def test_product_api_failure_manual_fallback_preserves_source(product, qtbot):
    p = product
    identity, stored = record(p, qtbot)
    transcribe(p, qtbot)
    before = authoritative(p, identity)
    existing = manual(p, identity, "Earlier history")
    p.provider.error = RuntimeError("controlled API failure")
    p.notes.submit(identity, config())
    qtbot.waitUntil(p.provider.entered.is_set)
    p.provider.allow_result.set()
    p.provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not p.notes.busy)
    assert p.notes.history(identity) == (existing,), "API failure corrupted history"
    assert p.storage.load(identity) == stored, "API failure mutated meeting"
    assert authoritative(p, identity) == before, "API failure mutated transcript"
    recovered = manual(p, identity, "Manual recovery")
    assert p.notes.manual_contexts[identity] == p.notes.prepare(identity)
    assert {a.summary_id for a in p.notes.history(identity)} == {
        existing.summary_id,
        recovered.summary_id,
    }
    p.notes.export(identity, recovered.summary_id, p.root / "recovered.txt")
    assert "Manual recovery" in (p.root / "recovered.txt").read_text(encoding="utf-8")
    assert authoritative(p, identity) == before


def test_product_stale_history_requires_acknowledgement(product, qtbot, monkeypatch):
    p = product
    identity, _ = record(p, qtbot)
    transcribe(p, qtbot)
    artifact = manual(p, identity, "Original notes")
    assert p.notes.freshness(artifact) is MeetingSummaryFreshness.FRESH
    # A newer authoritative profile is persisted by the real scheduler. While
    # its ASR is outstanding, the old summary must already cease to be fresh.
    p.final.request(
        identity,
        FinalTranscriptionConfig(profile_version=2, whisper_model_size="SMALL"),
    )
    qtbot.waitUntil(
        lambda: p.reader.load_generation_for_meeting(identity, 2) is not None
    )
    assert (
        p.notes.freshness(artifact) is not MeetingSummaryFreshness.FRESH
    ), "stale shown fresh"
    assert p.notes.history(identity) == (artifact,)
    destination = p.root / "stale.md"
    with pytest.raises(NotesError, match="Acknowledge"):
        p.notes.export(identity, artifact.summary_id, destination)
    panel = p.window.meeting_detail_widget.notes_panel
    panel.refresh()
    assert "Fresh" not in panel.provenance.text()
    dialog = Mock(return_value=(str(destination), "Markdown (*.md)"))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", dialog)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    panel.export()
    dialog.assert_not_called()
    assert not destination.exists()
    p.notes.export(identity, artifact.summary_id, destination, acknowledged=True)
    assert "Original notes" in destination.read_text(encoding="utf-8")
    transcribe(p, qtbot, fail=True, start=2)


def test_product_close_waits_for_sql_persistence_and_provider_release(
    product, qtbot, monkeypatch, qapp
):
    p = product
    identity, _ = record(p, qtbot)
    transcribe(p, qtbot)
    order = []
    save = p.summaries.save

    def persist(artifact):
        assert p.db.isOpen()
        save(artifact)
        order.append("persisted")

    def close_database():
        assert (
            p.notes.worker is None and p.notes.worker_thread is None
        ), "database closed with provider ownership"
        assert len(p.summaries.list_for_meeting(identity)) == 1
        order.append("database closed")
        p.db.close()

    monkeypatch.setattr(p.summaries, "save", persist)
    monkeypatch.setattr(qapp, "close_database", close_database, raising=False)
    p.window.show()
    p.notes.submit(identity, config())
    qtbot.waitUntil(p.provider.entered.is_set)
    worker, thread = p.notes.worker, p.notes.worker_thread
    order.append("close requested")
    assert not p.window.close()
    assert (
        p.db.isOpen() and p.notes.parent() is p.window
    ), "database closed with provider ownership"
    assert p.notes.worker is worker and p.notes.worker_thread is thread
    p.provider.allow_result.set()
    qtbot.waitUntil(p.provider.cleanup_entered.is_set)
    assert order == ["close requested", "persisted"]
    assert p.summaries.list_for_meeting(identity)[0].meeting_id == identity
    assert not p.window.close()  # shutdown(False) must retain ownership.
    assert p.db.isOpen() and p.notes.worker is worker
    p.provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not p.window.isVisible())
    assert order == ["close requested", "persisted", "database closed"]
    assert not p.db.isOpen()
    assert p.db.open()  # Permit normal fixture verification/teardown.
    monkeypatch.setattr(qapp, "close_database", lambda: None)
