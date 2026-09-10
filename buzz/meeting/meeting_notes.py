"""Owner-thread application service for durable meeting notes; no Qt or SQL."""
from __future__ import annotations

import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from buzz.meeting.final_transcription import FinalTranscriptionStatus
from buzz.meeting.meeting_detail import (
    MeetingDetailSnapshot,
    MeetingDetailTranscriptState as TS,
    MeetingDetailSpeakerReviewState as RS,
)
from buzz.meeting.meeting_summary import (
    MEETING_SUMMARY_SCHEMA_VERSION,
    MeetingSummary,
    MeetingSummaryArtifact,
    MeetingSummaryFreshness,
    check_freshness,
)
from buzz.meeting.meeting_summary_prompt import MEETING_SUMMARY_PROMPT_VERSION
from buzz.meeting.meeting_summary_provenance import (
    validate_meeting_summary_timestamp_provenance,
)
from buzz.meeting.summary_provider import (
    MeetingSummaryRequest,
    MeetingSummaryTranscriptEntry,
    validate_summary_provider_result,
)
from buzz.meeting.portable_ai_response import import_structured_ai_meeting_response
from buzz.meeting.portable_ai_response_repair import (
    import_repaired_structured_ai_meeting_response,
)
from buzz.meeting.meeting_minutes_export import (
    MeetingMinutesMetadata,
    write_meeting_minutes_markdown,
    write_meeting_minutes_text,
    write_meeting_minutes_docx,
)

# Fixed UI processing limit, in Unicode characters, applied before either parser.
MANUAL_RESPONSE_MAX_CHARS = 65_536


class NotesError(ValueError):
    """Safe, local application error."""


class SourceChangedError(NotesError):
    """Captured source no longer matches authoritative evidence."""


class DetailReader(Protocol):
    def load(self, meeting_id: uuid.UUID) -> MeetingDetailSnapshot:
        ...


class SummaryRepository(Protocol):
    def save(self, artifact: MeetingSummaryArtifact) -> None:
        ...

    def load(self, summary_id: uuid.UUID) -> MeetingSummaryArtifact | None:
        ...

    def list_for_meeting(
        self, meeting_id: uuid.UUID
    ) -> tuple[MeetingSummaryArtifact, ...]:
        ...


@dataclass(frozen=True, slots=True)
class NotesContext:
    meeting_id: uuid.UUID
    generation_id: uuid.UUID
    profile_version: int
    review_id: uuid.UUID | None
    review_revision: int | None
    request: MeetingSummaryRequest


@dataclass(frozen=True, slots=True)
class NotesCandidate:
    context: NotesContext
    artifact: MeetingSummaryArtifact


def assemble(snapshot: MeetingDetailSnapshot) -> NotesContext:
    generation, transcript = snapshot.final_generation, snapshot.transcript
    if (
        snapshot.transcript_state is not TS.AVAILABLE
        or generation is None
        or transcript is None
        or generation.status is not FinalTranscriptionStatus.COMPLETED
        or transcript.status is not FinalTranscriptionStatus.COMPLETED
        or generation.meeting_id != snapshot.meeting.session_id
        or transcript.meeting_id != generation.meeting_id
        or transcript.generation_id != generation.generation_id
    ):
        raise NotesError(
            "A complete final transcript is required. Check final transcription status or retry it."
        )
    review = (
        snapshot.speaker_review if snapshot.speaker_review_state is RS.FRESH else None
    )
    if review is not None and (
        review.source_generation_id != generation.generation_id
        or review.source_profile_version != generation.profile_version
    ):
        review = None
    names = (
        {}
        if review is None
        else {speaker.id: speaker.display_name for speaker in review.speakers}
    )
    assignments = {}
    if review is not None:
        for word in review.words:
            key = (word.word.source_role, word.word.source_segment_ordinal)
            assignments.setdefault(key, set()).add(
                word.effective_speaker_id if word.overridden else None
            )
    entries = []
    for segment in transcript.segments:
        ids = assignments.get(
            (segment.source_role, segment.source_track_ordinal), set()
        )
        name = names.get(next(iter(ids))) if len(ids) == 1 and None not in ids else None
        entries.append(
            MeetingSummaryTranscriptEntry(
                segment.text,
                segment.start_ns,
                segment.end_ns,
                name if name is not None and name.strip() else None,
            )
        )
    request = MeetingSummaryRequest(
        MEETING_SUMMARY_SCHEMA_VERSION, MEETING_SUMMARY_PROMPT_VERSION, tuple(entries)
    )
    return NotesContext(
        generation.meeting_id,
        generation.generation_id,
        generation.profile_version,
        None if review is None else review.id,
        None if review is None else review.revision,
        request,
    )


class MeetingNotesService:
    def __init__(self, detail: DetailReader, repository: SummaryRepository):
        self.detail = detail
        self.repository = repository

    def prepare(self, meeting_id: uuid.UUID) -> NotesContext:
        context = assemble(self.detail.load(meeting_id))
        if context.meeting_id != meeting_id:
            raise NotesError("Loaded transcript belongs to a different meeting.")
        return context

    def history(self, meeting_id):
        # Preserve repository ASC order; failure must propagate, never become [].
        return self.repository.list_for_meeting(meeting_id)

    def freshness(self, artifact):
        try:
            snapshot = self.detail.load(artifact.meeting_id)
        except Exception:
            return None  # Presentation: Cannot verify freshness.
        if snapshot.transcript_state in (
            TS.CORRUPT,
            TS.LOAD_FAILED,
        ) or snapshot.speaker_review_state in (RS.CORRUPT, RS.LOAD_FAILED):
            return None
        if snapshot.speaker_review_state is RS.STALE:
            return MeetingSummaryFreshness.STALE
        return check_freshness(
            artifact, snapshot.final_generation, snapshot.speaker_review
        )

    def import_response(self, context, text, *, repair=False):
        if context is None:
            raise NotesError("Copy an AI Request before importing its response.")
        if not isinstance(text, str) or len(text) > MANUAL_RESPONSE_MAX_CHARS:
            raise NotesError("Response exceeds the 65,536 character limit.")
        importer = (
            import_repaired_structured_ai_meeting_response
            if repair
            else import_structured_ai_meeting_response
        )
        return importer(context.request, text)

    def candidate(
        self, context: NotesContext, summary: MeetingSummary
    ) -> NotesCandidate:
        validate_summary_provider_result(context.request, summary)
        validate_meeting_summary_timestamp_provenance(context.request, summary)
        self._check_source(context)
        return NotesCandidate(
            context,
            MeetingSummaryArtifact(
                uuid.uuid4(),
                context.meeting_id,
                context.generation_id,
                context.profile_version,
                context.review_id,
                context.review_revision,
                datetime.now(timezone.utc),
                summary,
            ),
        )

    def _check_source(self, context):
        try:
            current = self.prepare(context.meeting_id)
        except Exception:
            raise SourceChangedError(
                "Source changed or cannot be verified. Copy a new request or generate again."
            ) from None
        if current != context:
            raise SourceChangedError(
                "Source changed. Copy a new request or generate again."
            )

    def save(self, candidate: NotesCandidate) -> MeetingSummaryArtifact:
        """The single Manual/API persistence boundary, also used for explicit retry."""
        context, artifact = candidate.context, candidate.artifact
        validate_summary_provider_result(context.request, artifact.summary)
        validate_meeting_summary_timestamp_provenance(context.request, artifact.summary)
        self._check_source(context)
        if (
            artifact.meeting_id,
            artifact.source_generation_id,
            artifact.source_profile_version,
            artifact.source_review_id,
            artifact.source_review_revision,
        ) != (
            context.meeting_id,
            context.generation_id,
            context.profile_version,
            context.review_id,
            context.review_revision,
        ):
            raise NotesError("Candidate provenance does not match its request.")
        self.repository.save(artifact)
        return artifact

    def selected(self, meeting_id, summary_id):
        artifact = self.repository.load(summary_id)
        if artifact is None or artifact.meeting_id != meeting_id:
            raise NotesError("Selected summary is unavailable for this meeting.")
        return artifact

    def export(self, meeting_id, summary_id, path: Path, *, acknowledged=False):
        artifact = self.selected(meeting_id, summary_id)
        if (
            self.freshness(artifact) is not MeetingSummaryFreshness.FRESH
            and not acknowledged
        ):
            raise NotesError(
                "Acknowledge unverified or older source notes before exporting."
            )
        meeting = self.detail.load(meeting_id).meeting
        metadata = MeetingMinutesMetadata(
            meeting_at=meeting.started_at or meeting.created_at,
            duration_ns=meeting.duration_ns,
        )
        writers = {
            ".md": write_meeting_minutes_markdown,
            ".txt": write_meeting_minutes_text,
            ".docx": write_meeting_minutes_docx,
        }
        writer = writers.get(path.suffix.lower())
        if writer is None:
            raise NotesError("Choose Markdown, Text, or DOCX.")
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=path.suffix, dir=path.parent
        )
        os.close(fd)
        try:
            writer(temporary, artifact.summary, metadata)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
