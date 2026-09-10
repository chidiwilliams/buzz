"""Reusable meeting-detail window backed by pure meeting services."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from buzz.locale import _
from buzz.meeting.final_transcription import FinalTranscriptionStatus
from buzz.meeting.meeting_audio_tracks import MeetingTrackRole
from buzz.meeting.meeting_detail import (
    MeetingDetailError,
    MeetingDetailLoadError,
    MeetingDetailNotFoundError,
    MeetingDetailService,
    MeetingDetailSnapshot,
    MeetingDetailSpeakerReviewState,
    MeetingDetailTranscriptState,
)
from buzz.meeting.meeting_storage import StoredMeetingAudioTrack
from buzz.meeting.speaker_review import (
    MeetingSpeakerReview,
    MeetingSpeakerReviewService,
    ReviewedSpeaker,
    ReviewedSpeakerWord,
    SpeakerReviewConfigError,
    SpeakerReviewError,
    SpeakerReviewNotFoundError,
    SpeakerReviewStaleError,
    SpeakerReviewStatus,
)
from buzz.widgets.meeting_presentation import (
    format_audio_status,
    format_duration,
    format_meeting_datetime,
    format_meeting_state,
    format_remote_source,
)


def _speaker_label(speaker: ReviewedSpeaker) -> str:
    return speaker.display_name or _("Speaker {number}").format(
        number=speaker.ordinal + 1
    )


class MeetingSpeakerWordTableModel(QAbstractTableModel):
    """Scalable word projection preserving the persisted aggregate order."""

    _HEADERS = (
        lambda: _("Time"),
        lambda: _("Word"),
        lambda: _("Speaker"),
        lambda: _("Assignment"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._words: tuple[ReviewedSpeakerWord, ...] = ()
        self._speakers: dict[uuid.UUID, ReviewedSpeaker] = {}

    def replace_review(self, review: MeetingSpeakerReview | None) -> None:
        self.beginResetModel()
        self._words = () if review is None else review.words
        self._speakers = (
            {}
            if review is None
            else {speaker.id: speaker for speaker in review.speakers}
        )
        self.endResetModel()

    def word_at(self, row: int) -> ReviewedSpeakerWord:
        if row < 0 or row >= len(self._words):
            raise IndexError("word row is out of range")
        return self._words[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._words)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self._HEADERS)
        ):
            return self._HEADERS[section]()
        return None

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        reviewed_word = self.word_at(index.row())
        word = reviewed_word.word
        speaker = self._speakers.get(reviewed_word.effective_speaker_id)
        speaker_text = "" if speaker is None else _speaker_label(speaker)
        if not reviewed_word.overridden:
            assignment = _("Inherited")
        elif reviewed_word.effective_speaker_id is None:
            assignment = _("Explicitly unassigned")
        else:
            assignment = _("Assigned")
        return (
            f"{word.local_start_ms / 1000:.2f}s",
            word.text,
            speaker_text,
            assignment,
        )[index.column()]


class MeetingDetailWidget(QWidget):
    """One reusable detail window; every refresh re-reads all aggregates."""

    def __init__(
        self,
        detail_service: MeetingDetailService,
        speaker_review_service: MeetingSpeakerReviewService,
        preview_player_factory: Callable[[Path], Any],
        parent: QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Widget,
        final_transcription=None,
        meeting_notes=None,
    ) -> None:
        super().__init__(parent, flags)
        self._detail_service = detail_service
        self._speaker_reviews = speaker_review_service
        self._preview_player_factory = preview_player_factory
        self._current_meeting_id: uuid.UUID | None = None
        self._snapshot: MeetingDetailSnapshot | None = None
        self._preview_player: Any | None = None
        self._final_transcription = final_transcription
        self._meeting_notes = meeting_notes
        self.notes_panel = None
        self.setWindowTitle(_("Meeting Details"))
        self.resize(1000, 760)
        self._build_ui()
        self._clear_presentation()

    def _build_ui(self) -> None:
        self.state_label = QLabel(self)

        metadata_group = QGroupBox(_("Meeting"), self)
        metadata_layout = QFormLayout(metadata_group)
        self.date_value = QLabel(metadata_group)
        self.duration_value = QLabel(metadata_group)
        self.source_value = QLabel(metadata_group)
        self.meeting_state_value = QLabel(metadata_group)
        self.audio_status_value = QLabel(metadata_group)
        metadata_layout.addRow(_("Date / Start"), self.date_value)
        metadata_layout.addRow(_("Duration"), self.duration_value)
        metadata_layout.addRow(_("Remote source"), self.source_value)
        metadata_layout.addRow(_("Meeting state"), self.meeting_state_value)
        metadata_layout.addRow(_("Audio status"), self.audio_status_value)

        audio_group = QGroupBox(_("Audio Tracks"), self)
        audio_layout = QVBoxLayout(audio_group)
        self.audio_table = QTableWidget(0, 6, audio_group)
        self.audio_table.setHorizontalHeaderLabels(
            [
                _("Role"),
                _("Asset"),
                _("Duration"),
                _("Recording state"),
                _("Published"),
                _("Complete"),
            ]
        )
        self.audio_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        audio_layout.addWidget(self.audio_table)

        transcript_group = QGroupBox(_("Final Transcript"), self)
        transcript_layout = QVBoxLayout(transcript_group)
        self.transcript_state_label = QLabel(transcript_group)
        self.transcript_edit = QPlainTextEdit(transcript_group)
        self.transcript_edit.setReadOnly(True)
        transcript_layout.addWidget(self.transcript_state_label)
        self.retry_transcription_button = QPushButton(
            _("Retry final transcription"), transcript_group
        )
        self.retry_transcription_button.setVisible(
            self._final_transcription is not None
        )
        self.retry_transcription_button.clicked.connect(self._retry_transcription)
        transcript_layout.addWidget(self.retry_transcription_button)
        transcript_layout.addWidget(self.transcript_edit)

        review_group = QGroupBox(_("Speaker Review"), self)
        review_layout = QVBoxLayout(review_group)
        self.review_state_label = QLabel(review_group)
        review_layout.addWidget(self.review_state_label)

        review_splitter = QSplitter(Qt.Orientation.Horizontal, review_group)
        speaker_panel = QWidget(review_splitter)
        speaker_layout = QVBoxLayout(speaker_panel)
        self.speaker_list = QListWidget(speaker_panel)
        self.speaker_list.currentRowChanged.connect(self._speaker_selection_changed)
        self.name_edit = QLineEdit(speaker_panel)
        speaker_buttons = QHBoxLayout()
        self.save_name_button = QPushButton(_("Save Name"), speaker_panel)
        self.add_speaker_button = QPushButton(_("Add Speaker"), speaker_panel)
        self.preview_button = QPushButton(_("Preview"), speaker_panel)
        speaker_buttons.addWidget(self.save_name_button)
        speaker_buttons.addWidget(self.add_speaker_button)
        speaker_buttons.addWidget(self.preview_button)
        self.merge_target_combo = QComboBox(speaker_panel)
        self.merge_button = QPushButton(_("Merge Into..."), speaker_panel)
        self.complete_button = QPushButton(_("Mark Review Complete"), speaker_panel)
        speaker_layout.addWidget(self.speaker_list)
        speaker_layout.addWidget(self.name_edit)
        speaker_layout.addLayout(speaker_buttons)
        speaker_layout.addWidget(self.merge_target_combo)
        speaker_layout.addWidget(self.merge_button)
        speaker_layout.addWidget(self.complete_button)

        word_panel = QWidget(review_splitter)
        word_layout = QVBoxLayout(word_panel)
        self.word_model = MeetingSpeakerWordTableModel(word_panel)
        self.word_table = QTableView(word_panel)
        self.word_table.setModel(self.word_model)
        self.word_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.word_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.word_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.assign_speaker_combo = QComboBox(word_panel)
        word_buttons = QHBoxLayout()
        self.assign_button = QPushButton(_("Assign to Speaker"), word_panel)
        self.unassign_button = QPushButton(_("Explicitly Unassign"), word_panel)
        self.clear_override_button = QPushButton(_("Clear Override"), word_panel)
        word_buttons.addWidget(self.assign_button)
        word_buttons.addWidget(self.unassign_button)
        word_buttons.addWidget(self.clear_override_button)
        word_layout.addWidget(self.word_table)
        word_layout.addWidget(self.assign_speaker_combo)
        word_layout.addLayout(word_buttons)
        review_splitter.addWidget(speaker_panel)
        review_splitter.addWidget(word_panel)
        review_layout.addWidget(review_splitter)
        self.mutation_error_label = QLabel(review_group)
        review_layout.addWidget(self.mutation_error_label)
        self.preview_host = QVBoxLayout()
        review_layout.addLayout(self.preview_host)

        self.save_name_button.clicked.connect(self._rename_speaker)
        self.add_speaker_button.clicked.connect(self._add_speaker)
        self.merge_button.clicked.connect(self._merge_speaker)
        self.preview_button.clicked.connect(self._preview_speaker)
        self.assign_button.clicked.connect(self._assign_word)
        self.unassign_button.clicked.connect(self._unassign_word)
        self.clear_override_button.clicked.connect(self._clear_word_override)
        self.complete_button.clicked.connect(self._mark_completed)

        layout = QVBoxLayout(self)
        if self._meeting_notes is not None:
            from buzz.widgets.meeting_notes_panel import MeetingNotesPanel
            from buzz.widgets.meeting_notes_configuration import NotesConfiguration

            tabs = QTabWidget(self)
            layout.addWidget(tabs)
            details = QWidget(tabs)
            layout = QVBoxLayout(details)
            tabs.addTab(details, _("Meeting"))
            self.notes_panel = MeetingNotesPanel(
                self._meeting_notes, NotesConfiguration(), tabs
            )
            tabs.addTab(self.notes_panel, _("AI Notes"))
        layout.addWidget(self.state_label)
        layout.addWidget(metadata_group)
        layout.addWidget(audio_group)
        layout.addWidget(transcript_group, 1)
        layout.addWidget(review_group, 2)

    def open_meeting(self, meeting_id: uuid.UUID) -> None:
        self._current_meeting_id = meeting_id
        self._snapshot = None
        self._clear_presentation()
        self.refresh()

    def refresh(self) -> None:
        if self._current_meeting_id is None:
            return
        if self.notes_panel is not None:
            self.notes_panel.open_meeting(self._current_meeting_id)
        meeting_id = self._current_meeting_id
        self._snapshot = None
        self._clear_presentation()
        try:
            snapshot = self._detail_service.load(meeting_id)
        except MeetingDetailNotFoundError:
            self.state_label.setText(_("Meeting not found."))
            return
        except MeetingDetailLoadError as exc:
            self.state_label.setText(
                _("Meeting data is corrupt.")
                if exc.corrupt
                else _("Could not load meeting.")
            )
            return
        except MeetingDetailError:
            logging.exception("Could not load meeting detail")
            self.state_label.setText(_("Could not load meeting."))
            return
        self._snapshot = snapshot
        self.state_label.clear()
        self._render(snapshot)

    def _clear_presentation(self) -> None:
        self.retry_transcription_button.setEnabled(False)
        self.state_label.clear()
        for label in (
            self.date_value,
            self.duration_value,
            self.source_value,
            self.meeting_state_value,
            self.audio_status_value,
            self.transcript_state_label,
            self.review_state_label,
            self.mutation_error_label,
        ):
            label.clear()
        self.audio_table.setRowCount(0)
        self.transcript_edit.clear()
        self.speaker_list.clear()
        self.name_edit.clear()
        self.merge_target_combo.clear()
        self.assign_speaker_combo.clear()
        self.word_model.replace_review(None)
        self._set_mutations_enabled(False)
        self._stop_preview()

    def _render(self, snapshot: MeetingDetailSnapshot) -> None:
        meeting = snapshot.meeting
        display_at = meeting.started_at or meeting.created_at
        self.date_value.setText(format_meeting_datetime(display_at))
        self.duration_value.setText(
            format_duration(
                None if meeting.duration_ns is None else meeting.duration_ns / 1e9
            )
        )
        self.source_value.setText(format_remote_source(meeting.remote_source_kind))
        self.meeting_state_value.setText(format_meeting_state(meeting.state))
        self.audio_status_value.setText(
            format_audio_status(meeting.audio_state, meeting.audio_outcome)
        )
        self._render_audio_tracks(
            tuple(
                track
                for track in (meeting.microphone, meeting.remote)
                if track is not None
            )
        )
        self._render_transcript(snapshot)
        self._render_review(snapshot)

    def _render_audio_tracks(self, tracks: tuple[StoredMeetingAudioTrack, ...]) -> None:
        self.audio_table.setRowCount(len(tracks))
        for row, track in enumerate(tracks):
            values = (
                _("Microphone")
                if track.role is MeetingTrackRole.MICROPHONE
                else _("Remote"),
                _("Available") if track.asset_exists_at_load else _("Missing"),
                format_duration(track.duration_seconds),
                track.recording_state.name.replace("_", " ").title(),
                _("Yes") if track.published else _("No"),
                _("Yes") if track.complete else _("No"),
            )
            for column, value in enumerate(values):
                self.audio_table.setItem(row, column, QTableWidgetItem(value))

    def _render_transcript(self, snapshot: MeetingDetailSnapshot) -> None:
        generation = snapshot.final_generation
        self.retry_transcription_button.setEnabled(
            self._final_transcription is not None
            and not self._final_transcription.pending
            and generation is not None
            and generation.status
            in (FinalTranscriptionStatus.FAILED, FinalTranscriptionStatus.PARTIAL)
        )
        state = snapshot.transcript_state
        if state is MeetingDetailTranscriptState.NOT_AVAILABLE:
            self.transcript_state_label.setText(_("Not available"))
            return
        if state is MeetingDetailTranscriptState.CORRUPT:
            self.transcript_state_label.setText(_("Transcript data is corrupt."))
            return
        if state is MeetingDetailTranscriptState.LOAD_FAILED:
            self.transcript_state_label.setText(_("Could not load transcript."))
            return
        generation = snapshot.final_generation
        assert generation is not None
        labels = {
            FinalTranscriptionStatus.QUEUED: _("Queued"),
            FinalTranscriptionStatus.IN_PROGRESS: _("In progress"),
            FinalTranscriptionStatus.COMPLETED: _("Completed"),
            FinalTranscriptionStatus.PARTIAL: _("Partial"),
            FinalTranscriptionStatus.FAILED: _("Failed"),
        }
        self.transcript_state_label.setText(labels[generation.status])
        if snapshot.transcript is not None:
            self.transcript_edit.setPlainText(
                "\n\n".join(segment.text for segment in snapshot.transcript.segments)
            )

    def _retry_transcription(self):
        if self._snapshot is None or self._snapshot.final_generation is None:
            return
        self._final_transcription.retry(self._snapshot.final_generation.generation_id)
        self.retry_transcription_button.setEnabled(False)

    def _render_review(self, snapshot: MeetingDetailSnapshot) -> None:
        labels = {
            MeetingDetailSpeakerReviewState.NOT_APPLICABLE: _("Not applicable"),
            MeetingDetailSpeakerReviewState.ABSENT: _("No speaker review"),
            MeetingDetailSpeakerReviewState.FRESH: _("Available"),
            MeetingDetailSpeakerReviewState.STALE: _("Speaker review is stale."),
            MeetingDetailSpeakerReviewState.CORRUPT: _("Speaker review is corrupt."),
            MeetingDetailSpeakerReviewState.LOAD_FAILED: _(
                "Could not load speaker review."
            ),
        }
        self.review_state_label.setText(labels[snapshot.speaker_review_state])
        review = snapshot.speaker_review
        self.word_model.replace_review(review)
        if review is None:
            self._set_mutations_enabled(False)
            return
        for speaker in review.speakers:
            item = QListWidgetItem(_speaker_label(speaker))
            item.setData(Qt.ItemDataRole.UserRole, speaker.id)
            self.speaker_list.addItem(item)
            self.assign_speaker_combo.addItem(_speaker_label(speaker), speaker.id)
        self._set_mutations_enabled(True)
        self.add_speaker_button.setEnabled(True)
        self.complete_button.setEnabled(
            review.status is not SpeakerReviewStatus.COMPLETED
        )
        if review.speakers:
            self.speaker_list.setCurrentRow(0)

    def _set_mutations_enabled(self, enabled: bool) -> None:
        for widget in (
            self.name_edit,
            self.save_name_button,
            self.add_speaker_button,
            self.merge_target_combo,
            self.merge_button,
            self.preview_button,
            self.assign_speaker_combo,
            self.assign_button,
            self.unassign_button,
            self.clear_override_button,
            self.complete_button,
        ):
            widget.setEnabled(enabled)

    def _review(self) -> MeetingSpeakerReview | None:
        return None if self._snapshot is None else self._snapshot.speaker_review

    def _selected_speaker(self) -> ReviewedSpeaker | None:
        review = self._review()
        item = self.speaker_list.currentItem()
        if review is None or item is None:
            return None
        speaker_id = item.data(Qt.ItemDataRole.UserRole)
        return next(
            (speaker for speaker in review.speakers if speaker.id == speaker_id), None
        )

    def _speaker_selection_changed(self, _row: int) -> None:
        review = self._review()
        selected = self._selected_speaker()
        self.merge_target_combo.clear()
        if review is None or selected is None:
            self.name_edit.clear()
            return
        self.name_edit.setText(selected.display_name or "")
        for speaker in review.speakers:
            if speaker.id != selected.id:
                self.merge_target_combo.addItem(_speaker_label(speaker), speaker.id)
        self.merge_button.setEnabled(self.merge_target_combo.count() > 0)
        self.preview_button.setEnabled(self._preview_candidate(selected) is not None)

    def _selected_word(self) -> ReviewedSpeakerWord | None:
        rows = self.word_table.selectionModel().selectedRows()
        return None if not rows else self.word_model.word_at(rows[0].row())

    def _rename_speaker(self) -> None:
        review, speaker = self._review(), self._selected_speaker()
        if review is None or speaker is None:
            return
        self._mutate(
            self._speaker_reviews.rename_speaker,
            review.id,
            speaker.id,
            self.name_edit.text(),
        )

    def _add_speaker(self) -> None:
        review = self._review()
        if review is not None:
            self._mutate(
                self._speaker_reviews.create_speaker,
                review.id,
                self.name_edit.text(),
            )

    def _merge_speaker(self) -> None:
        review, source = self._review(), self._selected_speaker()
        target_id = self.merge_target_combo.currentData()
        if review is None or source is None or target_id is None:
            return
        reply = QMessageBox.question(
            self,
            _("Merge Speakers"),
            _("Merge the selected speaker into the target speaker?"),
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._mutate(
                self._speaker_reviews.merge_speakers,
                review.id,
                source.id,
                target_id,
            )

    def _assign_word(self) -> None:
        review, word = self._review(), self._selected_word()
        speaker_id = self.assign_speaker_combo.currentData()
        if review is None or word is None or speaker_id is None:
            return
        self._mutate(
            self._speaker_reviews.assign_word,
            review.id,
            word.word.source_role,
            word.word.source_word_ordinal,
            speaker_id,
        )

    def _unassign_word(self) -> None:
        review, word = self._review(), self._selected_word()
        if review is not None and word is not None:
            self._mutate(
                self._speaker_reviews.unassign_word,
                review.id,
                word.word.source_role,
                word.word.source_word_ordinal,
            )

    def _clear_word_override(self) -> None:
        review, word = self._review(), self._selected_word()
        if review is not None and word is not None:
            self._mutate(
                self._speaker_reviews.clear_word_override,
                review.id,
                word.word.source_role,
                word.word.source_word_ordinal,
            )

    def _mark_completed(self) -> None:
        review = self._review()
        if review is not None:
            self._mutate(self._speaker_reviews.mark_completed, review.id)

    def _mutate(self, operation: Callable[..., object], *args: object) -> None:
        self.mutation_error_label.clear()
        try:
            operation(*args)
        except SpeakerReviewStaleError:
            self.refresh()
            return
        except SpeakerReviewNotFoundError:
            self.refresh()
            return
        except SpeakerReviewConfigError as exc:
            self.mutation_error_label.setText(str(exc))
            return
        except SpeakerReviewError:
            logging.exception("Could not update speaker review")
            self.mutation_error_label.setText(_("Could not update speaker review."))
            self.refresh()
            return
        self.refresh()

    def _preview_candidate(
        self, speaker: ReviewedSpeaker
    ) -> tuple[Path, int, int] | None:
        snapshot, review = self._snapshot, self._review()
        if snapshot is None or review is None:
            return None
        cluster_keys = {
            cluster.machine_speaker
            for cluster in review.clusters
            if cluster.reviewed_speaker_id == speaker.id
        }
        for turn in review.turns:
            if turn.local_end_ms <= turn.local_start_ms:
                continue
            if not any(
                key.source_role is turn.source_role
                and key.speaker_index == turn.speaker_index
                for key in cluster_keys
            ):
                continue
            track = (
                snapshot.meeting.microphone
                if turn.source_role is MeetingTrackRole.MICROPHONE
                else snapshot.meeting.remote
            )
            if track is None or not track.asset_exists_at_load:
                continue
            return track.path, turn.local_start_ms, turn.local_end_ms
        return None

    def _preview_speaker(self) -> None:
        speaker = self._selected_speaker()
        if speaker is None:
            return
        candidate = self._preview_candidate(speaker)
        if candidate is None:
            return
        path, start_ms, end_ms = candidate
        self._stop_preview()
        player = self._preview_player_factory(path)
        self._preview_player = player
        if isinstance(player, QWidget):
            self.preview_host.addWidget(player)
            player.show()
        player.set_range((start_ms, end_ms))
        player.toggle_play()

    def _stop_preview(self) -> None:
        player, self._preview_player = self._preview_player, None
        if player is None:
            return
        stop = getattr(player, "stop", None)
        if callable(stop):
            stop()
        if isinstance(player, QWidget):
            player.close()
            player.deleteLater()

    def closeEvent(self, event) -> None:
        if self.notes_panel is not None:
            self.notes_panel.closed = True
        self._stop_preview()
        super().closeEvent(event)


__all__ = ["MeetingDetailWidget", "MeetingSpeakerWordTableModel"]
