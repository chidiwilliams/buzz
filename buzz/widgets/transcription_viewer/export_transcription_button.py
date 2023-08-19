from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QPushButton, QWidget, QMenu, QFileDialog

from buzz.locale import _
from buzz.transcriber import (
    FileTranscriptionTask,
    OutputFormat,
    get_default_output_file_path,
    write_output,
)
from buzz.widgets.icon import FileDownloadIcon


class ExportTranscriptionButton(QPushButton):
    def __init__(self, transcription_task: FileTranscriptionTask, parent: QWidget):
        super().__init__(parent)
        self.transcription_task = transcription_task

        export_button_menu = QMenu()
        actions = [
            QAction(text=output_format.value.upper(), parent=self)
            for output_format in OutputFormat
        ]
        export_button_menu.addActions(actions)
        export_button_menu.triggered.connect(self.on_menu_triggered)

        self.setMenu(export_button_menu)
        self.setIcon(FileDownloadIcon(self))

    def on_menu_triggered(self, action: QAction):
        output_format = OutputFormat[action.text()]

        default_path = get_default_output_file_path(
            task=self.transcription_task, output_format=output_format
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
            segments=self.transcription_task.segments,
            output_format=output_format,
        )
