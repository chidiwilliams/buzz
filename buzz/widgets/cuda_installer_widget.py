"""
Dialog for installing GPU (CUDA) acceleration at runtime.
"""

import logging
from typing import Optional

from PyQt6.QtCore import QRunnable, QThreadPool, Qt, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QWidget,
)

from buzz.locale import _
from buzz.widgets.icon import BUZZ_ICON_PATH
from PyQt6.QtGui import QIcon

logger = logging.getLogger(__name__)


class _InstallSignals(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)


class _InstallWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = _InstallSignals()

    def run(self):
        try:
            from buzz.cuda_manager import install_cuda
            install_cuda(progress_callback=self.signals.progress.emit)
            self.signals.finished.emit()
        except Exception as exc:
            logger.exception("CUDA installation failed")
            self.signals.error.emit(str(exc))


class CudaInstallerDialog(QDialog):
    """Dialog that offers to install CUDA GPU acceleration."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(_("GPU Acceleration"))
        self.setWindowIcon(QIcon(BUZZ_ICON_PATH))
        self.setMinimumWidth(500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QLabel(_("Install GPU Acceleration?"))
        header.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            _(
                "An NVIDIA GPU was detected. Installing GPU acceleration allows Buzz "
                "to transcribe audio significantly faster using CUDA.\n\n"
                "This will download and install PyTorch with CUDA support (~2 GB). "
                "Buzz must be restarted after installation."
            )
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(120)
        self.log_view.setVisible(False)
        layout.addWidget(self.log_view)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        button_layout = QHBoxLayout()
        self.install_button = QPushButton(_("Install GPU Support"))
        self.install_button.setDefault(True)
        self.install_button.clicked.connect(self._on_install_clicked)

        self.decline_button = QPushButton(_("Not Now"))
        self.decline_button.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.decline_button)
        button_layout.addWidget(self.install_button)
        layout.addLayout(button_layout)

    def _on_install_clicked(self):
        self.install_button.setEnabled(False)
        self.decline_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log_view.setVisible(True)

        worker = _InstallWorker()
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error)

        QThreadPool.globalInstance().start(worker)

    def _on_progress(self, message: str):
        self.log_view.append(message)
        self.status_label.setText(message[:80])

    def _on_finished(self):
        self.progress_bar.setVisible(False)
        self.status_label.setText(
            _("Installation complete! Restart Buzz to enable GPU acceleration.")
        )
        self.install_button.setText(_("Close"))
        self.install_button.setEnabled(True)
        self.install_button.clicked.disconnect()
        self.install_button.clicked.connect(self.accept)

    def _on_error(self, error: str):
        self.progress_bar.setVisible(False)
        self.status_label.setText(_("Installation failed: {}").format(error))
        self.install_button.setEnabled(True)
        self.decline_button.setEnabled(True)
