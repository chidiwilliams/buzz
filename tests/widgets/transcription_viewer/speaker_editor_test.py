import uuid
from unittest.mock import MagicMock

import pytest
from PyQt6.QtGui import QFont, QPalette, QTextCursor
from PyQt6.QtWidgets import QTableView
from pytestqt.qtbot import QtBot

from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    Column,
    SPEAKER_COLORS,
    TranscriptionSegmentsEditorWidget,
)
from buzz.widgets.transcription_viewer.transcription_view_mode_tool_button import (
    ViewMode,
)
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)
from tests.audio import test_audio_path


@pytest.fixture()
def speaker_transcription(transcription_dao, transcription_segment_dao):
    transcription_id = uuid.uuid4()
    transcription_dao.insert(
        Transcription(
            id=str(transcription_id),
            status="completed",
            file=test_audio_path,
            task=Task.TRANSCRIBE.value,
            model_type=ModelType.WHISPER.value,
            whisper_model_size=WhisperModelSize.TINY.value,
        )
    )
    transcription_segment_dao.insert(
        TranscriptionSegment(
            0, 1000, "First statement.", "", str(transcription_id), "Nyomi"
        )
    )
    transcription_segment_dao.insert(
        TranscriptionSegment(
            1000, 2000, "Second statement.", "", str(transcription_id), "Nyomi"
        )
    )
    transcription_segment_dao.insert(
        TranscriptionSegment(
            2000, 3000, "A question.", "", str(transcription_id), "Mediator"
        )
    )
    return transcription_dao.find_by_id(str(transcription_id))


def test_speaker_column_supports_bulk_assignment(
    qtbot: QtBot, speaker_transcription, transcription_service
):
    widget = TranscriptionSegmentsEditorWidget(
        transcription_id=speaker_transcription.id_as_uuid,
        translator=MagicMock(),
        parent=None,
    )
    qtbot.add_widget(widget)

    assert widget.selectionMode() == QTableView.SelectionMode.ExtendedSelection
    assert widget.speaker_names() == ["Nyomi", "Mediator"]

    widget.assign_speaker_to_rows([2], "Nyomi")
    assert widget.model().record(2).value("speaker") == "Nyomi"
    assert widget.speaker_names() == ["Nyomi"]
    assert all(
        widget.model().record(row).value("speaker") == "Nyomi"
        for row in range(widget.model().rowCount())
    )


def test_speaker_delegate_accepts_a_new_name(
    qtbot: QtBot, speaker_transcription
):
    widget = TranscriptionSegmentsEditorWidget(
        transcription_id=speaker_transcription.id_as_uuid,
        translator=MagicMock(),
        parent=None,
    )
    qtbot.add_widget(widget)
    index = widget.model().index(0, Column.SPEAKER.value)
    editor = widget.speaker_delegate.createEditor(widget, None, index)
    editor.setEditText("New participant")

    widget.speaker_delegate.setModelData(editor, widget.model(), index)

    assert widget.model().record(0).value("speaker") == "New participant"


def test_speakers_view_is_colored_named_grouped_and_filterable(
    qtbot: QtBot,
    speaker_transcription,
    transcription_service,
    shortcuts,
):
    widget = TranscriptionViewerWidget(
        speaker_transcription, transcription_service, shortcuts
    )
    qtbot.add_widget(widget)

    assert widget.view_mode_tool_button.speakers_action.isEnabled()
    widget.on_view_mode_changed(ViewMode.SPEAKERS)
    rendered = widget.text_display_box.toPlainText()
    assert "● Nyomi" in rendered
    assert "First statement. Second statement." in rendered
    assert "● Mediator" in rendered

    nyomi_index = widget.speaker_filter_combo.findData("Nyomi")
    widget.speaker_filter_combo.setCurrentIndex(nyomi_index)
    filtered = widget.text_display_box.toPlainText()
    assert "First statement." in filtered
    assert "A question." not in filtered
    assert "● Nyomi" in filtered

    label_cursor = QTextCursor(widget.text_display_box.document())
    label_cursor.setPosition(0)
    label_cursor.movePosition(
        QTextCursor.MoveOperation.NextCharacter,
        QTextCursor.MoveMode.KeepAnchor,
    )
    assert label_cursor.selectedText() == "●"
    assert label_cursor.charFormat().foreground().color().name() == SPEAKER_COLORS[0].lower()
    widget.close()


def test_text_view_resets_speaker_label_formatting(
    qtbot: QtBot,
    speaker_transcription,
    transcription_service,
    shortcuts,
):
    widget = TranscriptionViewerWidget(
        speaker_transcription, transcription_service, shortcuts
    )
    qtbot.add_widget(widget)

    widget.on_view_mode_changed(ViewMode.SPEAKERS)
    widget.on_view_mode_changed(ViewMode.TEXT)

    text_cursor = QTextCursor(widget.text_display_box.document())
    text_cursor.setPosition(0)
    text_cursor.movePosition(
        QTextCursor.MoveOperation.NextCharacter,
        QTextCursor.MoveMode.KeepAnchor,
    )
    text_format = text_cursor.charFormat()
    assert text_format.fontWeight() == QFont.Weight.Normal
    assert text_format.foreground().color() == widget.text_display_box.palette().color(
        QPalette.ColorRole.Text
    )
    widget.close()


def test_audio_viewer_keeps_transcript_table_expanded(
    qtbot: QtBot,
    speaker_transcription,
    transcription_service,
    shortcuts,
):
    widget = TranscriptionViewerWidget(
        speaker_transcription, transcription_service, shortcuts
    )
    qtbot.add_widget(widget)
    widget.resize(1200, 900)
    widget.show()
    qtbot.waitUntil(lambda: sum(widget.media_splitter.sizes()) > 0)

    table_height, audio_height = widget.media_splitter.sizes()
    assert audio_height <= widget.AUDIO_PLAYER_MAX_HEIGHT
    assert table_height > audio_height * 4
    widget.close()


def test_colon_prefix_is_not_automatically_converted_to_a_speaker(
    qtbot: QtBot,
    transcription_dao,
    transcription_segment_dao,
    transcription_service,
    shortcuts,
):
    transcription_id = uuid.uuid4()
    transcription_dao.insert(
        Transcription(
            id=str(transcription_id),
            status="completed",
            file=test_audio_path,
            task=Task.TRANSCRIBE.value,
            model_type=ModelType.WHISPER.value,
            whisper_model_size=WhisperModelSize.TINY.value,
        )
    )
    transcription_segment_dao.insert(
        TranscriptionSegment(
            0,
            1000,
            "Nyomi: this remains ordinary transcript text.",
            "",
            str(transcription_id),
        )
    )
    transcription = transcription_dao.find_by_id(str(transcription_id))
    widget = TranscriptionViewerWidget(
        transcription, transcription_service, shortcuts
    )
    qtbot.add_widget(widget)

    assert widget.table_widget.speaker_names() == []
    assert not widget.view_mode_tool_button.speakers_action.isEnabled()
    assert widget.table_widget.model().record(0).value("speaker") == ""
    widget.close()
