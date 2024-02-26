import platform
from typing import Optional
from uuid import UUID

from PyQt6.QtCore import Qt
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtSql import QSqlRecord
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QGridLayout,
    QFileDialog,
)

from buzz.locale import _
from buzz.paths import file_path_as_title
from buzz.transcriber.file_transcriber import write_output
from buzz.transcriber.transcriber import OutputFormat, Segment, get_output_file_path
from buzz.widgets.audio_player import AudioPlayer
from buzz.widgets.transcription_record import TranscriptionRecord
from buzz.widgets.transcription_viewer.export_transcription_button import (
    ExportTranscriptionButton,
)
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    TranscriptionSegmentsEditorWidget,
)


class TranscriptionViewerWidget(QWidget):
    transcription: QSqlRecord

    def __init__(
        self,
        transcription: QSqlRecord,
        open_transcription_output=True,
        parent: Optional["QWidget"] = None,
        flags: Qt.WindowType = Qt.WindowType.Widget,
    ) -> None:
        super().__init__(parent, flags)
        self.transcription = transcription
        self.open_transcription_output = open_transcription_output

        self.setMinimumWidth(800)
        self.setMinimumHeight(500)

        self.setWindowTitle(file_path_as_title(transcription.value("file")))

        self.table_widget = TranscriptionSegmentsEditorWidget(
            transcription_id=UUID(hex=transcription.value("id")), parent=self
        )
        self.table_widget.segment_selected.connect(self.on_segment_selected)

        self.audio_player: Optional[AudioPlayer] = None
        if platform.system() != "Linux":
            self.audio_player = AudioPlayer(file_path=transcription.value("file"))
            self.audio_player.position_ms_changed.connect(
                self.on_audio_player_position_ms_changed
            )

        self.current_segment_label = QLabel()
        self.current_segment_label.setText("")
        self.current_segment_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.current_segment_label.setContentsMargins(0, 0, 0, 10)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        export_button = ExportTranscriptionButton(
            transcription=transcription, parent=self
        )
        export_button.on_export_triggered.connect(self.on_export_triggered)

        layout = QGridLayout(self)
        layout.addWidget(self.table_widget, 0, 0, 1, 2)

        if self.audio_player is not None:
            layout.addWidget(self.audio_player, 1, 0, 1, 1)
        layout.addWidget(export_button, 1, 1, 1, 1)
        layout.addWidget(self.current_segment_label, 2, 0, 1, 2)

        self.setLayout(layout)

    def on_export_triggered(self, output_format: OutputFormat) -> None:
        default_path = get_output_file_path(
            file_path=self.transcription.value("file"),
            task=TranscriptionRecord.task(self.transcription),
            language=self.transcription.value("language"),
            model=TranscriptionRecord.model(self.transcription),
            output_format=output_format,
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
            Segment(
                start=segment.value("start_time"),
                end=segment.value("end_time"),
                text=segment.value("text"),
            )
            for segment in self.table_widget.segments()
        ]

        write_output(
            path=output_file_path,
            segments=segments,
            output_format=output_format,
        )

    def on_segment_selected(self, segment: QSqlRecord):
        if self.audio_player is not None and (
            self.audio_player.media_player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.audio_player.set_range(
                (segment.value("start_time"), segment.value("end_time"))
            )

    def on_audio_player_position_ms_changed(self, position_ms: int) -> None:
        segments = self.table_widget.segments()
        current_segment = next(
            (
                segment
                for segment in segments
                if segment.value("start_time")
                <= position_ms
                < segment.value("end_time")
            ),
            None,
        )
        if current_segment is not None:
            self.current_segment_label.setText(current_segment.value("text"))
