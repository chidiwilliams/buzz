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

        actions = [
            QAction(text=output_format.value.upper(), parent=self)
            for output_format in OutputFormat
        ]
        self.addActions(actions)
        self.triggered.connect(self.on_menu_triggered)

    def on_menu_triggered(self, action: QAction):
        output_format = OutputFormat[action.text()]

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

        segments = [
            Segment(start=segment.start_time, end=segment.end_time, text=segment.text)
            for segment in self.transcription_service.get_transcription_segments(
                transcription_id=self.transcription.id_as_uuid
            )
        ]

        write_output(
            path=output_file_path,
            segments=segments,
            output_format=output_format,
        )
