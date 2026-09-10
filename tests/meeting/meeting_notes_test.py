from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import count
import uuid
from unittest.mock import Mock

import pytest
from buzz.meeting.meeting_notes import (
    MeetingNotesService,
    NotesError,
    SourceChangedError,
    assemble,
    MANUAL_RESPONSE_MAX_CHARS,
)
from buzz.meeting.meeting_detail import (
    MeetingDetailService,
    MeetingDetailSpeakerReviewState as RS,
    MeetingDetailTranscriptState as TS,
)
from buzz.meeting.final_transcription import (
    FinalTranscriptionStatus as FS,
    FinalTranscriptionDecodeError,
)
from buzz.meeting.meeting_summary import (
    MeetingSummary,
    MeetingSummaryFreshness as F,
    Participant,
)
from tests.meeting.meeting_detail_test import (
    Storage,
    Reader,
    Reviews,
    make_meeting,
    make_generation,
    make_transcript,
)
from tests.widgets.meeting_detail_widget_test import (
    snapshot,
    review,
    reviewed_word,
    SPEAKER_A,
    SPEAKER_B,
    MEETING_ID,
    DetailService,
)


def summary():
    return MeetingSummary(
        1, 1, "Planning", "We discussed the plan.", (), (), (), (), (), ()
    )


class Repository:
    def __init__(self):
        self.items = []
        self.attempts = []
        self.failure = None

    def save(self, artifact):
        self.attempts.append(artifact)
        if self.failure:
            raise self.failure
        assert artifact.summary_id not in {a.summary_id for a in self.items}
        self.items.append(artifact)
        self.items.sort(key=lambda a: (a.created_at, a.summary_id))

    def list_for_meeting(self, meeting_id):
        return tuple(a for a in self.items if a.meeting_id == meeting_id)

    def load(self, summary_id):
        return next((a for a in self.items if a.summary_id == summary_id), None)


@pytest.fixture
def notes(monkeypatch):
    deterministic_clock(monkeypatch)
    return MeetingNotesService(DetailService(snapshot()), Repository())


def deterministic_clock(monkeypatch):
    ticks = count()
    clock = Mock()
    clock.now.side_effect = lambda zone: datetime(
        2026, 1, 1, tzinfo=timezone.utc
    ) + timedelta(seconds=next(ticks))
    monkeypatch.setattr("buzz.meeting.meeting_notes.datetime", clock)


@pytest.mark.parametrize("status", [FS.QUEUED, FS.FAILED, FS.PARTIAL])
def test_authoritative_profile_two_blocks_profile_one(status):
    one, two = make_generation(1), make_generation(2, status)
    reader = Reader(((1, one), (2, two)), make_transcript(two))
    service = MeetingNotesService(
        MeetingDetailService(Storage(make_meeting()), reader, Reviews()), Repository()
    )
    with pytest.raises(NotesError):
        service.prepare(MEETING_ID)
    assert reader.discovery_calls == [(MEETING_ID, 2)]


def test_corrupt_profile_two_never_falls_back():
    reader = Reader(
        ((1, make_generation(1)), (2, FinalTranscriptionDecodeError("bad")))
    )
    service = MeetingNotesService(
        MeetingDetailService(Storage(make_meeting()), reader, Reviews()), Repository()
    )
    with pytest.raises(NotesError):
        service.prepare(MEETING_ID)
    assert reader.discovery_calls == [(MEETING_ID, 2)]


def test_profile_one_only_when_two_absent():
    one = make_generation(1)
    reader = Reader(((1, one),), make_transcript(one))
    service = MeetingNotesService(
        MeetingDetailService(Storage(make_meeting()), reader, Reviews()), Repository()
    )
    assert service.prepare(MEETING_ID).profile_version == 1
    assert reader.discovery_calls == [(MEETING_ID, 2), (MEETING_ID, 1)]


def test_canonical_order_and_meeting_nanoseconds():
    source = snapshot()
    segments = tuple(
        replace(s, start_ns=s.start_ns + 19_000_003, end_ns=s.end_ns + 19_000_003)
        for s in source.transcript.segments
    )
    context = assemble(
        replace(source, transcript=replace(source.transcript, segments=segments))
    )
    assert [
        (e.text, e.source_start_ns, e.source_end_ns) for e in context.request.transcript
    ] == [(s.text, s.start_ns, s.end_ns) for s in segments]


@pytest.mark.parametrize(
    "change",
    [
        "generation-meeting",
        "transcript-meeting",
        "generation-id",
        "empty",
        "blank",
        "partial",
        "missing",
    ],
)
def test_invalid_transcript_blocks(notes, change):
    source = snapshot()
    if change == "generation-meeting":
        source = replace(
            source,
            final_generation=replace(source.final_generation, meeting_id=uuid.uuid4()),
        )
    elif change == "missing":
        source = replace(source, transcript=None)
    else:
        transcript = source.transcript
        modifications = {
            "transcript-meeting": {"meeting_id": uuid.uuid4()},
            "generation-id": {"generation_id": uuid.uuid4()},
            "empty": {"segments": ()},
            "blank": {"segments": (replace(transcript.segments[0], text=" "),)},
            "partial": {"status": FS.PARTIAL},
        }
        source = replace(
            source, transcript=replace(transcript, **modifications[change])
        )
    with pytest.raises(Exception):
        assemble(source)
    assert not notes.repository.items


@pytest.mark.parametrize(
    "ids,expected",
    [
        ([SPEAKER_B] * 3, "Alice"),
        ([SPEAKER_B, SPEAKER_B, SPEAKER_A], None),
        ([SPEAKER_B, None], None),
        ([uuid.UUID(int=888)], None),
        ([SPEAKER_A], None),
        ([], None),
    ],
)
def test_unanimous_reviewed_identity_only(ids, expected):
    reviewed = replace(
        review(),
        words=tuple(reviewed_word(i, speaker, True) for i, speaker in enumerate(ids)),
    )
    context = assemble(snapshot(review_state=RS.FRESH, review_value=reviewed))
    assert context.request.transcript[0].speaker_name == expected
    assert (
        context.request.transcript[1].speaker_name is None
    )  # same segment ordinal, different role
    assert (context.review_id, context.review_revision) == (
        reviewed.id,
        reviewed.revision,
    )


@pytest.mark.parametrize(
    "words,expected",
    [
        ([(SPEAKER_B, True), (SPEAKER_B, True)], "Alice"),
        ([(SPEAKER_B, False), (SPEAKER_B, False)], None),
        ([(SPEAKER_B, True), (SPEAKER_B, False)], None),
        ([(SPEAKER_B, True), (SPEAKER_A, True)], None),
        ([(None, True)], None),
    ],
)
def test_segment_identity_requires_unanimous_explicit_assignments(words, expected):
    reviewed = replace(
        review(),
        words=tuple(
            reviewed_word(i, speaker_id, overridden)
            for i, (speaker_id, overridden) in enumerate(words)
        ),
    )
    context = assemble(snapshot(review_state=RS.FRESH, review_value=reviewed))
    assert context.request.transcript[0].speaker_name == expected
    assert (context.review_id, context.review_revision) == (
        reviewed.id,
        reviewed.revision,
    )


def test_explicit_assignment_with_blank_display_name_has_no_identity():
    reviewed = review()
    speakers = tuple(
        replace(speaker, display_name=" ") if speaker.id == SPEAKER_B else speaker
        for speaker in reviewed.speakers
    )
    reviewed = replace(
        reviewed,
        speakers=speakers,
        words=(reviewed_word(0, SPEAKER_B, True),),
    )
    context = assemble(snapshot(review_state=RS.FRESH, review_value=reviewed))
    assert context.request.transcript[0].speaker_name is None
    assert (context.review_id, context.review_revision) == (
        reviewed.id,
        reviewed.revision,
    )


@pytest.mark.parametrize("state", [RS.STALE, RS.CORRUPT, RS.LOAD_FAILED, RS.ABSENT])
def test_unavailable_review_uses_no_identity(state):
    context = assemble(snapshot(review_state=state))
    assert context.review_id is context.review_revision is None
    assert all(e.speaker_name is None for e in context.request.transcript)


@pytest.mark.parametrize(
    "change", ["text", "timestamps", "generation", "review", "read-failure"]
)
def test_pending_source_change_rejects_without_save(notes, change):
    context = notes.prepare(MEETING_ID)
    candidate = notes.candidate(context, summary())
    source = snapshot()
    if change == "text":
        source = replace(
            source,
            transcript=replace(
                source.transcript,
                segments=(replace(source.transcript.segments[0], text="changed"),),
            ),
        )
    elif change == "timestamps":
        source = replace(
            source,
            transcript=replace(
                source.transcript,
                segments=(replace(source.transcript.segments[0], end_ns=123),),
            ),
        )
    elif change == "generation":
        new_id = uuid.uuid4()
        source = replace(
            source,
            final_generation=replace(source.final_generation, generation_id=new_id),
            transcript=replace(source.transcript, generation_id=new_id),
        )
    elif change == "review":
        source = snapshot(review_state=RS.FRESH, review_value=review())
    else:
        source = RuntimeError("read failed")
    notes.detail = DetailService(source)
    with pytest.raises(SourceChangedError):
        notes.save(candidate)
    assert not notes.repository.attempts


def test_review_revision_captured_even_without_names(notes):
    reviewed = review()
    notes.detail = DetailService(snapshot(review_state=RS.FRESH, review_value=reviewed))
    context = notes.prepare(MEETING_ID)
    candidate = notes.candidate(context, summary())
    notes.detail = DetailService(
        snapshot(review_state=RS.FRESH, review_value=replace(reviewed, revision=1))
    )
    with pytest.raises(SourceChangedError):
        notes.save(candidate)


def test_insert_only_and_retry_same_candidate(notes):
    context = notes.prepare(MEETING_ID)
    first = notes.save(notes.candidate(context, summary()))
    candidate = notes.candidate(context, summary())
    notes.repository.failure = RuntimeError("DB unavailable")
    with pytest.raises(RuntimeError):
        notes.save(candidate)
    notes.repository.failure = None
    assert notes.save(candidate) is candidate.artifact
    assert notes.repository.attempts[-1] is notes.repository.attempts[-2]
    assert notes.history(MEETING_ID) == (first, candidate.artifact)
    assert first.summary_id != candidate.artifact.summary_id


@pytest.mark.parametrize(
    "state,expected",
    [
        (RS.ABSENT, F.FRESH),
        (RS.STALE, F.STALE),
        (RS.CORRUPT, None),
        (RS.LOAD_FAILED, None),
        (RS.FRESH, F.INDETERMINATE),
    ],
)
def test_freshness_truthful(notes, state, expected):
    artifact = notes.candidate(notes.prepare(MEETING_ID), summary()).artifact
    notes.detail = DetailService(
        snapshot(
            review_state=state, review_value=review() if state is RS.FRESH else None
        )
    )
    assert notes.freshness(artifact) is expected


def test_failed_transcript_read_never_fresh(notes):
    artifact = notes.candidate(notes.prepare(MEETING_ID), summary()).artifact
    for value in (RuntimeError("unreadable"), snapshot(transcript_state=TS.CORRUPT)):
        notes.detail = DetailService(value)
        assert notes.freshness(artifact) is None


def test_history_corruption_propagates(notes):
    notes.repository.list_for_meeting = Mock(side_effect=ValueError("corrupt"))
    with pytest.raises(ValueError):
        notes.history(MEETING_ID)


def test_provider_identity_fabrication_rejected(notes):
    result = replace(summary(), participants=(Participant("Alice", uuid.uuid4()),))
    with pytest.raises(Exception):
        notes.candidate(notes.prepare(MEETING_ID), result)
    assert not notes.repository.attempts


def test_manual_requires_context_strict_then_explicit_repair(notes):
    from buzz.meeting.meeting_summary import meeting_summary_to_json

    text = meeting_summary_to_json(summary())
    context = notes.prepare(MEETING_ID)
    with pytest.raises(NotesError):
        notes.import_response(None, text)
    with pytest.raises(Exception):
        notes.import_response(context, f"```json\n{text}\n```")
    assert (
        notes.import_response(context, f"```json\n{text}\n```", repair=True)
        == summary()
    )
    for repair in (False, True):
        with pytest.raises(NotesError):
            notes.import_response(
                context, "x" * (MANUAL_RESPONSE_MAX_CHARS + 1), repair=repair
            )
        with pytest.raises(Exception):
            notes.import_response(context, "invalid", repair=repair)
    assert not notes.repository.attempts


@pytest.mark.parametrize("suffix", [".md", ".txt", ".docx"])
def test_export_exact_historical_summary(notes, tmp_path, suffix):
    first = notes.save(notes.candidate(notes.prepare(MEETING_ID), summary()))
    notes.save(
        notes.candidate(
            notes.prepare(MEETING_ID),
            replace(summary(), summary="Latest different summary"),
        )
    )
    destination = tmp_path / ("minutes" + suffix)
    notes.export(MEETING_ID, first.summary_id, destination)
    if suffix == ".docx":
        from zipfile import ZipFile

        with ZipFile(destination) as z:
            result = z.read("word/document.xml").decode()
    else:
        result = destination.read_text(encoding="utf8")
    assert "We discussed the plan." in result
    assert "Latest different summary" not in result
    assert len(notes.repository.items) == 2


def test_export_atomic_and_no_summary_guard(notes, tmp_path, monkeypatch):
    destination = tmp_path / "minutes.md"
    destination.write_text("existing")
    with pytest.raises(NotesError):
        notes.export(MEETING_ID, uuid.uuid4(), destination)
    first = notes.save(notes.candidate(notes.prepare(MEETING_ID), summary()))
    with pytest.raises(NotesError):
        notes.export(uuid.uuid4(), first.summary_id, destination)

    def broken(path, *args):
        from pathlib import Path

        Path(path).write_text("partial")
        raise RuntimeError()

    monkeypatch.setattr(
        "buzz.meeting.meeting_notes.write_meeting_minutes_markdown", broken
    )
    with pytest.raises(RuntimeError):
        notes.export(MEETING_ID, first.summary_id, destination)
    assert destination.read_text() == "existing"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("freshness", [F.STALE, F.INDETERMINATE, None])
def test_export_requires_acknowledgement(notes, tmp_path, monkeypatch, freshness):
    first = notes.save(notes.candidate(notes.prepare(MEETING_ID), summary()))
    monkeypatch.setattr(notes, "freshness", lambda _: freshness)
    path = tmp_path / "minutes.txt"
    with pytest.raises(NotesError):
        notes.export(MEETING_ID, first.summary_id, path)
    assert not path.exists()
    notes.export(MEETING_ID, first.summary_id, path, acknowledged=True)
    assert path.exists()


def test_requested_meeting_identity_is_verified(notes):
    with pytest.raises(NotesError):
        notes.prepare(uuid.uuid4())


def test_application_service_has_no_qt_or_qsql_imports():
    import ast
    from pathlib import Path

    tree = ast.parse(Path("buzz/meeting/meeting_notes.py").read_text(encoding="utf8"))
    modules = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    modules += [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert not any(
        name.startswith(("PyQt", "buzz.db", "buzz.widgets")) for name in modules
    )
