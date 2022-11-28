from model_loader import ModelLoader
from PyQt6.QtCore import (QDateTime, QRunnable, QObject, QRect, QSettings, Qt, QTimer,
                          QUrl, pyqtSignal, pyqtSlot, QThreadPool, QThread)
from PyQt6.QtGui import (QAction, QCloseEvent, QDesktopServices, QIcon,
                         QKeySequence, QPixmap, QTextCursor)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QGridLayout, QLabel, QMainWindow,
                             QMessageBox, QPlainTextEdit, QProgressDialog,
                             QPushButton, QVBoxLayout, QWidget)
import logging

class TestWorker:
    def test_should_work(self):
        worker = ModelLoader(name='tiny')
        worker.signals.progress.connect(logging.debug)
        worker.signals.completed.connect(logging.debug)
        pool = QThreadPool()
        pool.start(worker)
        pool.waitForDone()
