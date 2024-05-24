import platform
from typing import Optional
from uuid import UUID

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtSql import QSqlRecord
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QToolButton,
    QLabel,
)

from buzz.locale import _
from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.paths import file_path_as_title
from buzz.settings.shortcuts import Shortcuts
from buzz.widgets.audio_player import AudioPlayer
from buzz.widgets.icon import (
    FileDownloadIcon,
)
from buzz.widgets.text_display_box import TextDisplayBox
from buzz.widgets.toolbar import ToolBar
from buzz.widgets.transcription_viewer.export_transcription_menu import (
    ExportTranscriptionMenu,
)
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    TranscriptionSegmentsEditorWidget,
)
from buzz.widgets.transcription_viewer.transcription_view_mode_tool_button import (
    TranscriptionViewModeToolButton,
)


class TranscriptionViewerWidget(QWidget):
    transcription: Transcription

    def __init__(
        self,
        transcription: Transcription,
        transcription_service: TranscriptionService,
        shortcuts: Shortcuts,
        parent: Optional["QWidget"] = None,
        flags: Qt.WindowType = Qt.WindowType.Widget,
    ) -> None:
        super().__init__(parent, flags)
        self.transcription = transcription
        self.transcription_service = transcription_service

        self.setMinimumWidth(800)
        self.setMinimumHeight(500)

        self.setWindowTitle(file_path_as_title(transcription.file))

        self.is_showing_timestamps = True

        self.table_widget = TranscriptionSegmentsEditorWidget(
            transcription_id=UUID(hex=transcription.id), parent=self
        )
        self.table_widget.segment_selected.connect(self.on_segment_selected)

        self.text_display_box = TextDisplayBox(self)
        font = QFont(self.text_display_box.font().family(), 14)
        self.text_display_box.setFont(font)

        self.audio_player: Optional[AudioPlayer] = None
        if platform.system() != "Linux":
            self.audio_player = AudioPlayer(file_path=transcription.file)
            self.audio_player.position_ms_changed.connect(
                self.on_audio_player_position_ms_changed
            )

        self.current_segment_label = QLabel("", self)
        self.current_segment_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.current_segment_label.setContentsMargins(0, 0, 0, 10)

        layout = QVBoxLayout(self)

        toolbar = ToolBar(self)

        view_mode_tool_button = TranscriptionViewModeToolButton(shortcuts, self)
        view_mode_tool_button.view_mode_changed.connect(self.on_view_mode_changed)
        toolbar.addWidget(view_mode_tool_button)

        export_tool_button = QToolButton()
        export_tool_button.setText(_("Export"))
        export_tool_button.setIcon(FileDownloadIcon(self))
        export_tool_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )

        export_transcription_menu = ExportTranscriptionMenu(
            transcription, transcription_service, self
        )
        export_tool_button.setMenu(export_transcription_menu)
        export_tool_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(export_tool_button)

        layout.setMenuBar(toolbar)

        layout.addWidget(self.table_widget)
        layout.addWidget(self.text_display_box)
        if self.audio_player is not None:
            layout.addWidget(self.audio_player)
        layout.addWidget(self.current_segment_label)

        self.setLayout(layout)

        self.reset_view()

    def reset_view(self):
        if self.is_showing_timestamps:
            self.text_display_box.hide()
            self.table_widget.show()
        else:
            segments = self.transcription_service.get_transcription_segments(
                transcription_id=self.transcription.id_as_uuid
            )
            self.text_display_box.setPlainText(
                " ".join(segment.text.strip() for segment in segments)
            )
            self.text_display_box.show()
            self.table_widget.hide()

    def on_view_mode_changed(self, is_timestamps: bool) -> None:
        self.is_showing_timestamps = is_timestamps
        self.reset_view()

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
