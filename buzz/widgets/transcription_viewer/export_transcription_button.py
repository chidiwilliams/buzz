from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QPushButton, QWidget, QMenu

from buzz.transcriber.transcriber import (
    OutputFormat,
)
from buzz.widgets.icon import FileDownloadIcon


class ExportTranscriptionButton(QPushButton):
    on_export_triggered = pyqtSignal(OutputFormat)

    def __init__(self, parent: QWidget):
        super().__init__(parent)

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
        self.on_export_triggered.emit(output_format)
