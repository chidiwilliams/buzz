import logging
import os
from PyQt6.QtGui import QAction
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QMenu, QFileDialog, QMessageBox

from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.locale import _
from buzz.paths import safe_filename_component
from buzz.transcriber.file_transcriber import write_output
from buzz.transcriber.docx_writer import write_speaker_docx
from buzz.transcriber.transcriber import (
    OutputFormat,
    Segment,
)


class ExportTranscriptionMenu(QMenu):
    def __init__(
        self,
        transcription: Transcription,
        transcription_service: TranscriptionService,
        has_translation: bool,
        translation: pyqtSignal,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.transcription = transcription
        self.transcription_service = transcription_service

        translation.connect(self.on_translation_available)

        text_label = _("Text")
        translation_label = _("Translation")
        self.text_actions = [
            QAction(text=f"{output_format.value.upper()} - {text_label}", parent=self)
            for output_format in OutputFormat
        ]
        self.translation_actions = [
            QAction(text=f"{output_format.value.upper()} - {translation_label}", parent=self)
            for output_format in OutputFormat
        ]
        for action in self.translation_actions:
            action.setVisible(has_translation)
        actions = self.text_actions + self.translation_actions
        self.addActions(actions)

        self.addSeparator()
        self.speaker_docx_action = QAction(
            text=_("DOCX – Speakers"),
            parent=self,
        )
        self.addAction(self.speaker_docx_action)
        self.aboutToShow.connect(self._refresh_speaker_docx_action)
        self._refresh_speaker_docx_action()
        self.triggered.connect(self.on_menu_triggered)

    @staticmethod
    def extract_format_and_segment_key(action_text: str):
        parts = action_text.split('-')
        output_format = parts[0].strip()
        label = parts[1].strip() if len(parts) > 1 else None
        segment_key = 'translation' if label == _('Translation') else 'text'

        return output_format, segment_key

    def on_translation_available(self):
        for action in self.translation_actions:
            action.setVisible(True)

    def on_menu_triggered(self, action: QAction):
        if action == self.speaker_docx_action:
            self.export_speakers_docx()
            return

        segments = [
            Segment(
                start=segment.start_time,
                end=segment.end_time,
                text=segment.text,
                translation=segment.translation,
                speaker=segment.speaker)
            for segment in self.transcription_service.get_transcription_segments(
                transcription_id=self.transcription.id_as_uuid
            )
        ]

        output_format_value, segment_key = self.extract_format_and_segment_key(action.text())
        output_format = OutputFormat(output_format_value.lower())

        default_path = self.transcription.get_output_file_path(
            output_format=output_format
        )

        (output_file_path, nil) = QFileDialog.getSaveFileName(
            self,
            _("Save File"),
            default_path,
            _("Text files") + f" (*.{output_format.value})",
        )

        if output_file_path == "":
            return

        write_output(
            path=output_file_path,
            segments=segments,
            output_format=output_format,
            segment_key=segment_key
        )

    def _refresh_speaker_docx_action(self):
        segments = self.transcription_service.get_transcription_segments(
            transcription_id=self.transcription.id_as_uuid
        )
        self.speaker_docx_action.setEnabled(
            any((segment.speaker or "").strip() for segment in segments)
        )

    def export_speakers_docx(self):
        segments = self.transcription_service.get_transcription_segments(
            transcription_id=self.transcription.id_as_uuid
        )
        if not any((segment.speaker or "").strip() for segment in segments):
            return

        timestamp_choice = QMessageBox.question(
            self,
            _("DOCX – Speakers"),
            _("Include timestamps for each speaker turn?"),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
        )
        if timestamp_choice == QMessageBox.StandardButton.Cancel:
            return

        source_path = self.transcription.file or "transcript"
        source_directory = os.path.dirname(source_path)
        source_title = (
            self.transcription.name
            or os.path.splitext(os.path.basename(source_path))[0]
            or "transcript"
        )
        source_stem = safe_filename_component(source_title)
        default_path = os.path.join(
            source_directory,
            f"{source_stem}_speakers.docx",
        )
        output_file_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            _("Save File"),
            default_path,
            _("Word documents") + " (*.docx)",
        )
        if not output_file_path:
            return
        if not output_file_path.lower().endswith(".docx"):
            output_file_path += ".docx"

        try:
            write_speaker_docx(
                output_file_path,
                source_title,
                segments,
                include_timestamps=(
                    timestamp_choice == QMessageBox.StandardButton.Yes
                ),
                unassigned_label=_("Unassigned"),
            )
        except Exception as exc:
            logging.exception("Failed to export speaker DOCX")
            QMessageBox.critical(
                self,
                _("Export Failed"),
                str(exc),
            )
