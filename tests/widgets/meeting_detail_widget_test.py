from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import QAbstractTableModel
from PyQt6.QtWidgets import QApplication, QMessageBox

from buzz.locale import _ as translate
from buzz.meeting.final_transcription import (
    FinalTranscriptionConfig,
    FinalTranscriptionGeneration,
    FinalTranscriptionStatus,
    MeetingTranscript,
    MeetingTranscriptSegment,
    MeetingTranscriptWord,
)
from buzz.meeting.meeting_audio_tracks import (
    MeetingAudioTracksOutcome,
    MeetingAudioTracksState,
    MeetingTrackRole,
)
from buzz.meeting.meeting_detail import (
    MeetingDetailLoadError,
    MeetingDetailSnapshot,
    MeetingDetailSpeakerReviewState,
    MeetingDetailTranscriptState,
)
from buzz.meeting.meeting_recorder import MeetingRecorderState
from buzz.meeting.meeting_session import MeetingRemoteSourceKind, MeetingSessionState
from buzz.meeting.meeting_storage import StoredMeeting, StoredMeetingAudioTrack
from buzz.meeting.speaker_diarization import SpeakerDiarizationBackend
from buzz.meeting.speaker_mapping import (
    MeetingSpeakerKey,
    SpeakerAttributionStatus,
)
from buzz.meeting.speaker_review import (
    MeetingSpeakerReview,
    ReviewedSpeaker,
    ReviewedSpeakerWord,
    SpeakerReviewAnalysisState,
    SpeakerReviewCluster,
    SpeakerReviewStaleError,
    SpeakerReviewStatus,
    SpeakerReviewTrack,
    SpeakerReviewTurn,
)
from buzz.widgets.meeting_detail_widget import (
    MeetingDetailWidget,
    MeetingSpeakerWordTableModel,
)


MEETING_ID = uuid.UUID(int=17)
REVIEW_ID = uuid.UUID(int=18)
SPEAKER_A = uuid.UUID(int=19)
SPEAKER_B = uuid.UUID(int=20)
MIC_PATH = Path("C:/durable/microphone.wav")
REMOTE_PATH = Path("C:/durable/remote.wav")


@pytest.fixture(scope="session")
def qapp_cls():
    return QApplication


def track(role, path, *, exists=True):
    return StoredMeetingAudioTrack(
        role=role,
        relative_path=PurePosixPath(path.name),
        path=path,
        sample_rate=16_000,
        sample_count=32_000,
        recording_state=MeetingRecorderState.STOPPED,
        published=True,
        complete=True,
        timing_basis="host_callback_arrival",
        timing_anchors=(),
        errors=(),
        asset_exists_at_load=exists,
    )


def meeting(*, mic_exists=True, remote_exists=True):
    return StoredMeeting(
        session_id=MEETING_ID,
        remote_source_kind=MeetingRemoteSourceKind.SYSTEM,
        state=MeetingSessionState.COMPLETED,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
        duration_ns=2_000_000_000,
        audio_state=MeetingAudioTracksState.STOPPED,
        audio_outcome=MeetingAudioTracksOutcome.COMPLETE,
        microphone=track(MeetingTrackRole.MICROPHONE, MIC_PATH, exists=mic_exists),
        remote=track(MeetingTrackRole.REMOTE, REMOTE_PATH, exists=remote_exists),
    )


def generation(status=FinalTranscriptionStatus.COMPLETED):
    return FinalTranscriptionGeneration(
        generation_id=uuid.UUID(int=21),
        meeting_id=MEETING_ID,
        profile_version=2,
        status=status,
        config=FinalTranscriptionConfig(profile_version=2, whisper_model_size="LARGE"),
        tracks=(),
    )


def transcript(status=FinalTranscriptionStatus.COMPLETED):
    return MeetingTranscript(
        generation_id=uuid.UUID(int=21),
        meeting_id=MEETING_ID,
        status=status,
        segments=(
            MeetingTranscriptSegment(
                0,
                MeetingTrackRole.MICROPHONE,
                0,
                0,
                100,
                0,
                100_000_000,
                "phrase one",
            ),
            MeetingTranscriptSegment(
                1,
                MeetingTrackRole.REMOTE,
                0,
                100,
                200,
                100_000_000,
                200_000_000,
                "phrase two",
            ),
        ),
    )


def reviewed_word(ordinal, effective, overridden):
    word = MeetingTranscriptWord(
        MeetingTrackRole.MICROPHONE,
        0,
        ordinal,
        ordinal * 100,
        ordinal * 100 + 80,
        ordinal * 100_000_000,
        ordinal * 100_000_000 + 80_000_000,
        f"word-{ordinal}",
    )
    return ReviewedSpeakerWord(
        word,
        SpeakerAttributionStatus.ASSIGNED,
        MeetingSpeakerKey(MeetingTrackRole.MICROPHONE, 7),
        effective,
        overridden,
    )


def review(*, speakers=None, turns=None, status=SpeakerReviewStatus.IN_PROGRESS):
    speaker_values = (
        (
            ReviewedSpeaker(SPEAKER_A, 0, None),
            ReviewedSpeaker(SPEAKER_B, 1, "Alice"),
        )
        if speakers is None
        else speakers
    )
    return MeetingSpeakerReview(
        id=REVIEW_ID,
        source_generation_id=uuid.UUID(int=21),
        source_profile_version=2,
        source_track_count=2,
        mapping_algorithm_version=1,
        status=status,
        revision=0,
        next_speaker_ordinal=len(speaker_values),
        time_created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        time_updated=datetime(2026, 1, 1, tzinfo=timezone.utc),
        time_completed=None,
        tracks=(
            SpeakerReviewTrack(
                MeetingTrackRole.MICROPHONE,
                Mock(),
                3,
                SpeakerReviewAnalysisState.COMPLETED,
                2,
                SpeakerDiarizationBackend.MSDD,
                1,
            ),
        ),
        turns=(
            (
                SpeakerReviewTurn(MeetingTrackRole.MICROPHONE, 0, 7, 100, 200),
                SpeakerReviewTurn(MeetingTrackRole.REMOTE, 0, 9, 300, 450),
            )
            if turns is None
            else turns
        ),
        clusters=(
            SpeakerReviewCluster(
                MeetingSpeakerKey(MeetingTrackRole.MICROPHONE, 7), SPEAKER_A
            ),
            SpeakerReviewCluster(
                MeetingSpeakerKey(MeetingTrackRole.REMOTE, 9), SPEAKER_A
            ),
        ),
        speakers=speaker_values,
        words=(
            reviewed_word(2, SPEAKER_A, False),
            reviewed_word(0, SPEAKER_B, True),
            reviewed_word(1, None, True),
        ),
    )


def snapshot(
    *,
    transcript_state=MeetingDetailTranscriptState.AVAILABLE,
    generation_value=None,
    transcript_value=None,
    review_state=MeetingDetailSpeakerReviewState.NOT_APPLICABLE,
    review_value=None,
    meeting_value=None,
):
    if (
        generation_value is None
        and transcript_state is MeetingDetailTranscriptState.AVAILABLE
    ):
        generation_value = generation()
    if (
        transcript_value is None
        and transcript_state is MeetingDetailTranscriptState.AVAILABLE
    ):
        if generation_value.status in (
            FinalTranscriptionStatus.COMPLETED,
            FinalTranscriptionStatus.PARTIAL,
        ):
            transcript_value = transcript(generation_value.status)
    return MeetingDetailSnapshot(
        meeting=meeting_value or meeting(),
        transcript_state=transcript_state,
        final_generation=generation_value,
        transcript=transcript_value,
        speaker_review_state=review_state,
        speaker_review=review_value,
    )


class DetailService:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def load(self, meeting_id):
        self.calls.append(meeting_id)
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


class PreviewPlayer:
    def __init__(self):
        self.ranges = []
        self.toggles = 0
        self.stops = 0

    def set_range(self, value):
        self.ranges.append(value)

    def toggle_play(self):
        self.toggles += 1

    def stop(self):
        self.stops += 1


def make_widget(qtbot, detail, speaker_service=None, factory=None):
    widget = MeetingDetailWidget(
        detail,
        speaker_service or Mock(),
        factory or Mock(return_value=PreviewPlayer()),
    )
    qtbot.add_widget(widget)
    return widget


@pytest.mark.parametrize("status", list(FinalTranscriptionStatus))
def test_final_retry_button_uses_existing_generation(qtbot, status):
    final = Mock(pending=0)
    value = snapshot(generation_value=generation(status))
    widget = MeetingDetailWidget(
        DetailService(value), Mock(), Mock(), final_transcription=final
    )
    qtbot.addWidget(widget)
    widget.open_meeting(MEETING_ID)
    retryable = status in (
        FinalTranscriptionStatus.FAILED,
        FinalTranscriptionStatus.PARTIAL,
    )
    assert widget.retry_transcription_button.isEnabled() == retryable
    if retryable:
        widget.retry_transcription_button.click()
        final.retry.assert_called_once_with(value.final_generation.generation_id)
        assert not widget.retry_transcription_button.isEnabled()
    else:
        final.retry.assert_not_called()


def open_widget(qtbot, value, speaker_service=None, factory=None):
    detail = DetailService(value)
    widget = make_widget(qtbot, detail, speaker_service, factory)
    widget.open_meeting(MEETING_ID)
    return widget, detail


def test_metadata_and_audio_tracks_render_without_paths(qtbot) -> None:
    widget, _ = open_widget(
        qtbot,
        snapshot(meeting_value=meeting(remote_exists=False)),
    )
    assert widget.duration_value.text() == "2s"
    assert widget.source_value.text() == "System audio"
    assert widget.meeting_state_value.text() == translate("Completed")
    assert widget.audio_status_value.text() == translate("Complete")
    assert widget.audio_table.rowCount() == 2
    assert widget.audio_table.item(0, 1).text() == translate("Available")
    assert widget.audio_table.item(1, 1).text() == translate("Missing")
    rendered = " ".join(
        widget.audio_table.item(row, column).text()
        for row in range(2)
        for column in range(6)
    )
    assert "C:/" not in rendered


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (MeetingDetailTranscriptState.NOT_AVAILABLE, "Not available"),
        (MeetingDetailTranscriptState.CORRUPT, "Transcript data is corrupt."),
        (MeetingDetailTranscriptState.LOAD_FAILED, "Could not load transcript."),
    ],
)
def test_transcript_section_failure_states(qtbot, state, expected) -> None:
    widget, _ = open_widget(qtbot, snapshot(transcript_state=state))
    assert widget.transcript_state_label.text() == translate(expected)
    assert widget.transcript_edit.toPlainText() == ""


@pytest.mark.parametrize("status", list(FinalTranscriptionStatus))
def test_generation_lifecycle_and_phrase_transcript(qtbot, status) -> None:
    generation_value = generation(status)
    widget, _ = open_widget(
        qtbot,
        snapshot(generation_value=generation_value),
    )
    expected = {
        FinalTranscriptionStatus.QUEUED: "Queued",
        FinalTranscriptionStatus.IN_PROGRESS: "In progress",
        FinalTranscriptionStatus.COMPLETED: "Completed",
        FinalTranscriptionStatus.PARTIAL: "Partial",
        FinalTranscriptionStatus.FAILED: "Failed",
    }[status]
    assert widget.transcript_state_label.text() == translate(expected)
    if status in (FinalTranscriptionStatus.COMPLETED, FinalTranscriptionStatus.PARTIAL):
        assert widget.transcript_edit.toPlainText() == "phrase one\n\nphrase two"
    else:
        assert widget.transcript_edit.toPlainText() == ""


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (MeetingDetailSpeakerReviewState.NOT_APPLICABLE, "Not applicable"),
        (MeetingDetailSpeakerReviewState.ABSENT, "No speaker review"),
        (MeetingDetailSpeakerReviewState.STALE, "Speaker review is stale."),
        (MeetingDetailSpeakerReviewState.CORRUPT, "Speaker review is corrupt."),
        (MeetingDetailSpeakerReviewState.LOAD_FAILED, "Could not load speaker review."),
    ],
)
def test_nonfresh_review_states_disable_mutations(qtbot, state, expected) -> None:
    widget, _ = open_widget(qtbot, snapshot(review_state=state))
    assert widget.review_state_label.text() == translate(expected)
    assert not widget.add_speaker_button.isEnabled()
    assert not widget.assign_button.isEnabled()


def test_fresh_review_fallback_labels_word_order_and_assignment_distinction(
    qtbot,
) -> None:
    review_value = review()
    widget, _ = open_widget(
        qtbot,
        snapshot(
            review_state=MeetingDetailSpeakerReviewState.FRESH,
            review_value=review_value,
        ),
    )
    assert [widget.speaker_list.item(row).text() for row in range(2)] == [
        translate("Speaker {number}").format(number=1),
        "Alice",
    ]
    assert "MICROPHONE:7" not in widget.speaker_list.item(0).text()
    assert [widget.word_model.word_at(row) for row in range(3)] == list(
        review_value.words
    )
    assert [widget.word_model.index(row, 3).data() for row in range(3)] == [
        "Inherited",
        "Assigned",
        "Explicitly unassigned",
    ]
    assert all(
        widget.word_table.indexWidget(widget.word_model.index(row, 0)) is None
        for row in range(3)
    )


def test_zero_speaker_review_allows_add_and_completed_disables_complete(qtbot) -> None:
    empty = review(speakers=())
    widget, _ = open_widget(
        qtbot,
        snapshot(
            review_state=MeetingDetailSpeakerReviewState.FRESH,
            review_value=empty,
        ),
    )
    assert widget.add_speaker_button.isEnabled()
    completed = replace(empty, status=SpeakerReviewStatus.COMPLETED)
    widget._detail_service.results[0] = snapshot(
        review_state=MeetingDetailSpeakerReviewState.FRESH,
        review_value=completed,
    )
    widget.refresh()
    assert not widget.complete_button.isEnabled()


def test_mutations_use_exact_service_arguments_and_full_refresh(qtbot) -> None:
    review_value = review()
    snap = snapshot(
        review_state=MeetingDetailSpeakerReviewState.FRESH,
        review_value=review_value,
    )
    service = Mock()
    widget, detail = open_widget(qtbot, snap, service)

    widget.name_edit.setText("Bob")
    widget.save_name_button.click()
    service.rename_speaker.assert_called_once_with(REVIEW_ID, SPEAKER_A, "Bob")

    widget.name_edit.setText("Manual")
    widget.add_speaker_button.click()
    service.create_speaker.assert_called_once_with(REVIEW_ID, "Manual")

    widget.word_table.selectRow(0)
    widget.assign_speaker_combo.setCurrentIndex(1)
    widget.assign_button.click()
    service.assign_word.assert_called_once_with(
        REVIEW_ID, MeetingTrackRole.MICROPHONE, 2, SPEAKER_B
    )
    widget.word_table.selectRow(0)
    widget.unassign_button.click()
    service.unassign_word.assert_called_once_with(
        REVIEW_ID, MeetingTrackRole.MICROPHONE, 2
    )
    widget.word_table.selectRow(0)
    widget.clear_override_button.click()
    service.clear_word_override.assert_called_once_with(
        REVIEW_ID, MeetingTrackRole.MICROPHONE, 2
    )
    widget.complete_button.click()
    service.mark_completed.assert_called_once_with(REVIEW_ID)
    assert len(detail.calls) == 7


def test_merge_has_one_confirmation_and_exact_arguments(qtbot) -> None:
    service = Mock()
    widget, _ = open_widget(
        qtbot,
        snapshot(
            review_state=MeetingDetailSpeakerReviewState.FRESH,
            review_value=review(),
        ),
        service,
    )
    with patch.object(
        QMessageBox,
        "question",
        return_value=QMessageBox.StandardButton.Yes,
    ) as question:
        widget.merge_button.click()
    question.assert_called_once()
    service.merge_speakers.assert_called_once_with(REVIEW_ID, SPEAKER_A, SPEAKER_B)


def test_stale_mutation_forces_refresh_and_disables_controls(qtbot) -> None:
    fresh = snapshot(
        review_state=MeetingDetailSpeakerReviewState.FRESH,
        review_value=review(),
    )
    stale = snapshot(review_state=MeetingDetailSpeakerReviewState.STALE)
    detail = DetailService(fresh, stale)
    service = Mock()
    service.rename_speaker.side_effect = SpeakerReviewStaleError("stale")
    widget = make_widget(qtbot, detail, service)
    widget.open_meeting(MEETING_ID)

    widget.save_name_button.click()

    assert widget.review_state_label.text() == translate("Speaker review is stale.")
    assert not widget.save_name_button.isEnabled()
    assert detail.calls == [MEETING_ID, MEETING_ID]


def test_preview_uses_first_persisted_valid_turn_and_exact_stored_path(qtbot) -> None:
    turns = (
        SpeakerReviewTurn(MeetingTrackRole.MICROPHONE, 0, 7, 50, 50),
        SpeakerReviewTurn(MeetingTrackRole.REMOTE, 0, 9, 300, 450),
        SpeakerReviewTurn(MeetingTrackRole.MICROPHONE, 1, 7, 100, 250),
    )
    review_value = review(turns=turns)
    factory = Mock(side_effect=[PreviewPlayer(), PreviewPlayer()])
    widget, _ = open_widget(
        qtbot,
        snapshot(
            review_state=MeetingDetailSpeakerReviewState.FRESH,
            review_value=review_value,
        ),
        factory=factory,
    )

    widget.preview_button.click()
    first_player = widget._preview_player
    factory.assert_called_once_with(REMOTE_PATH)
    assert first_player.ranges == [(300, 450)]
    assert first_player.toggles == 1

    widget.preview_button.click()
    assert first_player.stops == 1
    assert factory.call_count == 2


def test_preview_skips_missing_assets_and_manual_only_speakers(qtbot) -> None:
    manual = ReviewedSpeaker(uuid.UUID(int=99), 9, "Manual")
    review_value = replace(review(), speakers=review().speakers + (manual,))
    widget, _ = open_widget(
        qtbot,
        snapshot(
            meeting_value=meeting(mic_exists=False, remote_exists=False),
            review_state=MeetingDetailSpeakerReviewState.FRESH,
            review_value=review_value,
        ),
    )
    assert not widget.preview_button.isEnabled()
    widget.speaker_list.setCurrentRow(2)
    assert not widget.preview_button.isEnabled()


def test_open_a_then_b_failure_clears_old_presentation(qtbot) -> None:
    detail = DetailService(snapshot(), MeetingDetailLoadError("bad"))
    widget = make_widget(qtbot, detail)
    widget.open_meeting(MEETING_ID)
    assert widget.transcript_edit.toPlainText() == "phrase one\n\nphrase two"

    other = uuid.UUID(int=999)
    widget.open_meeting(other)

    assert widget._current_meeting_id == other
    assert widget._snapshot is None
    assert widget.state_label.text() == translate("Could not load meeting.")
    assert widget.transcript_edit.toPlainText() == ""


def test_word_model_is_qabstract_table_model_without_widgets() -> None:
    assert issubclass(MeetingSpeakerWordTableModel, QAbstractTableModel)
