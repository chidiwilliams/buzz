import logging
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QWidget, QMenu, QFileDialog

from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.locale import _
from buzz.transcriber.file_transcriber import write_output
from buzz.transcriber.transcriber import (
    OutputFormat,
    Segment,
)


class ExportTranscriptionMenu(QMenu):
    def __init__(
        self,
        transcription: Transcription,
        transcription_service: TranscriptionService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.transcription = transcription
        self.transcription_service = transcription_service
        self.segments = []
        self.load_segments()

        if self.segments and len(self.segments[0].translation) > 0:
            text_label = _("Text")
            translation_label = _("Translation")
            actions = [
                action
                for output_format in OutputFormat
                for action in [
                    QAction(text=f"{output_format.value.upper()} - {text_label}", parent=self),
                    QAction(text=f"{output_format.value.upper()} - {translation_label}", parent=self)
                ]
            ]
        else:
            actions = [
                QAction(text=output_format.value.upper(), parent=self)
                for output_format in OutputFormat
            ]
        self.addActions(actions)
        self.triggered.connect(self.on_menu_triggered)

    def load_segments(self):
        self.segments = [
            Segment(
                start=segment.start_time,
                end=segment.end_time,
                text=segment.text,
                translation=segment.translation)
            for segment in self.transcription_service.get_transcription_segments(
                transcription_id=self.transcription.id_as_uuid
            )
        ]
    @staticmethod
    def extract_format_and_segment_key(action_text: str):
        parts = action_text.split('-')
        output_format = parts[0].strip()
        label = parts[1].strip() if len(parts) > 1 else None
        segment_key = 'translation' if label == _('Translation') else 'text'

        return output_format, segment_key

    def on_menu_triggered(self, action: QAction):
        output_format_value, segment_key = self.extract_format_and_segment_key(action.text())
        output_format = OutputFormat[output_format_value]

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

        # Reload segments in case they were resized
        self.load_segments()

        write_output(
            path=output_file_path,
            segments=self.segments,
            output_format=output_format,
            segment_key=segment_key
        )
