"""Opt-in fault injection plugin, loaded only by run_meeting_release_mutations.

Each case changes a production boundary in memory, then runs an unchanged
product scenario in a fresh process. Nothing edits production files on disk.
"""

from dataclasses import replace
import json
import os
from pathlib import Path
import uuid

import pytest
from PyQt6.QtSql import QSqlQuery
from PyQt6.QtWidgets import QMessageBox


CASES = {
    "stop-ai-before-save": "happy_path_selected_persisted_minutes",
    "skip-meeting-persistence": "happy_path_selected_persisted_minutes",
    "wrong-result-meeting": "happy_path_selected_persisted_minutes",
    "partial-to-failed": "remote_degradation_preserves_microphone",
    "retry-wrong-generation": "final_failure_explicit_retry_same_generation",
    "api-failure-mutates-source": "api_failure_manual_fallback_preserves_source",
    "manual-wrong-context": "api_failure_manual_fallback_preserves_source",
    "overwrite-summary-history": "happy_path_selected_persisted_minutes",
    "stale-as-fresh": "stale_history_requires_acknowledgement",
    "export-latest-not-selected": "happy_path_selected_persisted_minutes",
    "database-close-with-provider": "close_waits_for_sql_persistence_and_provider_release",
}

ORACLES = {
    "stop-ai-before-save": "stop implicitly triggered AI",
    "skip-meeting-persistence": "meeting persistence skipped",
    "wrong-result-meeting": "API result not persisted for originating meeting",
    "partial-to-failed": "PARTIAL coerced",
    "retry-wrong-generation": "authoritative transcript unavailable",
    "api-failure-mutates-source": "API failure mutated meeting",
    "manual-wrong-context": "SourceChangedError: Source changed.",
    "overwrite-summary-history": "summary history overwritten",
    "stale-as-fresh": "stale shown fresh",
    "export-latest-not-selected": "selected artifact not exported",
    "database-close-with-provider": "database closed with provider ownership",
}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    name = os.environ["BUZZ_RELEASE_MUTATION"]
    if report.when == "call" and report.failed and ORACLES[name] in report.longreprtext:
        # Mutants intentionally violate lifetime/save contracts and may leave
        # owned threads. Record the actual expected test failure before ending
        # this disposable process; do not run broken-state Qt teardown. Normal
        # product tests still exercise their complete lifecycle and teardown.
        Path(os.environ["BUZZ_RELEASE_ORACLE"]).write_text(
            json.dumps(
                {
                    "mutation": name,
                    "nodeid": report.nodeid,
                    "oracle": ORACLES[name],
                    "failure": report.longreprtext,
                }
            ),
            encoding="utf-8",
        )
        os._exit(42)


@pytest.fixture(autouse=True)
def inject_release_mutation(product, monkeypatch):
    # Plugin import precedes conftest's user-data sandbox; Buzz imports belong
    # here, after fixture setup, never at plugin module scope.
    from buzz.meeting.final_transcription import FinalTranscriptionConfig
    from buzz.meeting.meeting_audio_tracks import MeetingAudioTracksOutcome
    from buzz.meeting.meeting_summary import MeetingSummaryFreshness
    from buzz.meeting.summary_provider import (
        MeetingSummaryRequest,
        MeetingSummaryTranscriptEntry,
    )

    name = os.environ["BUZZ_RELEASE_MUTATION"]
    assert name in CASES
    p = product

    def sql(statement, *values):
        query = QSqlQuery(p.db)
        assert query.prepare(statement)
        for value in values:
            query.addBindValue(value)
        assert query.exec(), query.lastError().text()

    if name == "stop-ai-before-save":
        stop = p.capture.workflow.stop_capture

        def eager_ai():
            p.provider.allow_result.set()
            p.provider.summarize(
                MeetingSummaryRequest(
                    1,
                    1,
                    (
                        MeetingSummaryTranscriptEntry(
                            "provisional live text", 0, 100, None
                        ),
                    ),
                )
            )
            stop()

        monkeypatch.setattr(p.capture.workflow, "stop_capture", eager_ai)
    elif name == "skip-meeting-persistence":
        monkeypatch.setattr(
            p.storage._repository, "atomic_replace", lambda *a, **k: None
        )
        # Keep the real error path noninteractive; this is the external dialog.
        monkeypatch.setattr(
            QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok
        )
        monkeypatch.setattr(
            QMessageBox, "critical", lambda *a, **k: QMessageBox.StandardButton.Ok
        )
    elif name == "wrong-result-meeting":
        candidate = p.notes.service.candidate

        def wrong_result(context, summary):
            value = candidate(context, summary)
            return replace(
                value, artifact=replace(value.artifact, meeting_id=uuid.uuid4())
            )

        monkeypatch.setattr(p.notes.service, "candidate", wrong_result)
    elif name == "partial-to-failed":
        decode = p.storage._decode_bundle

        def coerce(*args, **kwargs):
            stored = decode(*args, **kwargs)
            if stored.audio_outcome is MeetingAudioTracksOutcome.PARTIAL:
                stored = replace(stored, audio_outcome=MeetingAudioTracksOutcome.FAILED)
            return stored

        monkeypatch.setattr(p.storage, "_decode_bundle", coerce)
    elif name == "retry-wrong-generation":

        def new_generation(generation_id):
            generation = p.reader.load_generation(generation_id)
            p.final.request(
                generation.meeting_id,
                FinalTranscriptionConfig(profile_version=2, whisper_model_size="SMALL"),
            )

        monkeypatch.setattr(p.final, "retry", new_generation)
    elif name == "api-failure-mutates-source":

        def corrupt_source(meeting_id, message):
            if message.startswith("API generation failed"):
                sql(
                    "UPDATE meeting SET duration_ns = duration_ns + 1 WHERE id = ?",
                    str(meeting_id),
                )

        p.notes.status.connect(corrupt_source)
    elif name == "manual-wrong-context":
        copy = p.notes.copy_request

        def wrong_context(meeting_id, *args, **kwargs):
            result = copy(meeting_id, *args, **kwargs)
            # Activate on fallback, leaving the preexisting summary untouched.
            if p.provider.error is not None:
                p.notes.manual_contexts[meeting_id] = replace(
                    p.notes.manual_contexts[meeting_id], generation_id=uuid.uuid4()
                )
            return result

        monkeypatch.setattr(p.notes, "copy_request", wrong_context)
    elif name == "overwrite-summary-history":
        save = p.summaries.save

        def overwrite(artifact):
            sql(
                "DELETE FROM meeting_summary WHERE meeting_id = ?",
                str(artifact.meeting_id),
            )
            save(artifact)

        monkeypatch.setattr(p.summaries, "save", overwrite)
    elif name == "stale-as-fresh":
        monkeypatch.setattr(
            p.notes, "freshness", lambda _: MeetingSummaryFreshness.FRESH
        )
    elif name == "export-latest-not-selected":
        export = p.notes.service.export

        def latest(meeting_id, summary_id, path, **kwargs):
            return export(
                meeting_id, p.notes.history(meeting_id)[-1].summary_id, path, **kwargs
            )

        monkeypatch.setattr(p.notes.service, "export", latest)
    elif name == "database-close-with-provider":
        from buzz.widgets.main_window import MainWindow

        close = MainWindow.closeEvent

        def premature_close(window, event):
            if p.notes.busy:
                # A real database close, before MainWindow checks AI ownership.
                p.db.close()
            close(window, event)

        monkeypatch.setattr(MainWindow, "closeEvent", premature_close)
    yield
    # Restore behavior before the product fixture releases owned resources.
    monkeypatch.undo()
    if not p.db.isOpen():
        assert p.db.open()
