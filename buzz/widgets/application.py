import sys
import darkdetect

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor

from buzz.__version__ import VERSION
from buzz.db.dao.transcription_dao import TranscriptionDAO
from buzz.db.dao.transcription_segment_dao import TranscriptionSegmentDAO
from buzz.db.db import setup_app_db
from buzz.db.service.transcription_service import TranscriptionService
from buzz.settings.settings import APP_NAME, Settings

from buzz.transcriber.transcriber import FileTranscriptionTask
from buzz.widgets.main_window import MainWindow


class Application(QApplication):
    window: MainWindow

    def __init__(self, argv: list) -> None:
        super().__init__(argv)

        self.setApplicationName(APP_NAME)
        self.setApplicationVersion(VERSION)
        self.hide_main_window = False

        if sys.platform.startswith("win") and darkdetect.isDark():
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor("#121212"))
            palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#2e2e2e"))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#000000"))
            palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.Button, QColor("#1e1e1e"))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.BrightText, QColor("#ff0000"))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))

            self.setPalette(palette)

            # For Windows 11
            stylesheet = """
            QWidget {
                background-color: #121212;
                color: #ffffff;
            }
            QPushButton {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #2e2e2e;
            }
            QHeaderView::section {
                background-color: #1e1e1e;
                color: #ffffff;
                font-weight: bold;
            }
            QToolBar {
                border: 1px solid #2e2e2e;
            }
            QTabBar::tab {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QTabBar::tab:selected {
                background-color: #2e2e2e;
            }
            QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, 
            QTabWidget::pane, QFormLayout, QHBoxLayout, QVBoxLayout, QTreeWidget,
            QTableView, QGroupBox {
                border: 1px solid #2e2e2e;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
            QTabWidget::pane:focus, QFormLayout:focus, QHBoxLayout:focus, QVBoxLayout:focus, QTreeWidget:focus,
            QTableView:focus, QGroupBox:focus {
                border: 1px solid #4e4e4e;
            }
            QMenuBar {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QMenuBar::item {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QMenuBar::item:selected {
                background-color: #2e2e2e;
            }
            QMenu::item {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QMenu::item:selected {
                background-color: #2e2e2e;
            }
            QMenu::item:hover {
                background-color: #2e2e2e;
            }
            QToolButton {
                background-color: transparent;
                min-height: 30px;
                min-width: 30px;
            }
            QToolButton:hover {
                background-color: #2e2e2e; 
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 16px;
                margin: 16px 0 16px 0;
            }
            QScrollBar::handle:vertical {
                background-color: #2e2e2e;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical {
                background-color: #1e1e1e;
                height: 16px;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
            }
            QScrollBar::sub-line:vertical {
                background-color: #1e1e1e;
                height: 16px;
                subcontrol-position: top;
                subcontrol-origin: margin;
            }
            QScrollBar:horizontal {
                background-color: #1e1e1e;
                height: 16px;
                margin: 0 16px 0 16px;
            }
            QScrollBar::handle:horizontal {
                background-color: #2e2e2e;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal {
                background-color: #1e1e1e;
                width: 16px;
                subcontrol-position: right;
                subcontrol-origin: margin;
            }
            QScrollBar::sub-line:horizontal {
                background-color: #1e1e1e;
                width: 16px;
                subcontrol-position: left;
                subcontrol-origin: margin;
            }
            QScrollBar::sub-page:horizontal, QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:vertical, QScrollBar::add-page:vertical {
                background-color: #1e1e1e;
            }           
            """
            self.setStyleSheet(stylesheet)

        self.settings = Settings()
        font_size = self.settings.value(
            key=Settings.Key.FONT_SIZE, default_value=self.font().pointSize()
        )

        if sys.platform == "darwin":
            self.setFont(QFont("SF Pro", font_size))
        else:
            self.setFont(QFont(self.font().family(), font_size))

        db = setup_app_db()
        transcription_service = TranscriptionService(
            TranscriptionDAO(db), TranscriptionSegmentDAO(db)
        )

        self.window = MainWindow(transcription_service)

    def show_main_window(self):
        if not self.hide_main_window:
            self.window.show()

    def add_task(self, task: FileTranscriptionTask, quit_on_complete: bool = False):
        self.window.quit_on_complete = quit_on_complete
        self.window.add_task(task)
