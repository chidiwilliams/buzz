from typing import Optional, List, Tuple

from PyQt6 import QtGui
from PyQt6.QtCore import pyqtSignal, Qt, QThreadPool
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
)

from buzz.dialogs import show_model_download_error_dialog
from buzz.locale import _
from buzz.model_loader import ModelDownloader
from buzz.paths import file_path_as_title
from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_password, Key
from buzz.transcriber.transcriber import (
    FileTranscriptionOptions,
    TranscriptionOptions,
)
from buzz.widgets.model_download_progress_dialog import ModelDownloadProgressDialog
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)
from buzz.widgets.transcriber.file_transcription_form_widget import (
    FileTranscriptionFormWidget,
)


class FileTranscriberWidget(QWidget):
    model_download_progress_dialog: Optional[ModelDownloadProgressDialog] = None
    model_loader: Optional[ModelDownloader] = None
    file_transcription_options: FileTranscriptionOptions
    transcription_options: TranscriptionOptions
    is_transcribing = False
    # (TranscriptionOptions, FileTranscriptionOptions, str)
    triggered = pyqtSignal(tuple)
    openai_access_token_changed = pyqtSignal(str)
    settings = Settings()

    def __init__(
        self,
        file_paths: Optional[List[str]] = None,
        url: Optional[str] = None,
        parent: Optional[QWidget] = None,
        flags: Qt.WindowType = Qt.WindowType.Widget,
    ) -> None:
        super().__init__(parent, flags)

        self.url = url
        self.file_paths = file_paths

        self.setWindowTitle(self.get_title())

        openai_access_token = get_password(Key.OPENAI_API_KEY)

        preferences = self.load_preferences()

        (
            self.transcription_options,
            self.file_transcription_options,
        ) = preferences.to_transcription_options(
            openai_access_token=openai_access_token,
            file_paths=self.file_paths,
            url=url,
        )

        layout = QVBoxLayout(self)

        self.form_widget = FileTranscriptionFormWidget(
            transcription_options=self.transcription_options,
            file_transcription_options=self.file_transcription_options,
            parent=self,
        )
        self.form_widget.openai_access_token_changed.connect(
            self.openai_access_token_changed
        )

        self.run_button = QPushButton(_("Run"), self)
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.on_click_run)

        layout.addWidget(self.form_widget)
        layout.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignRight)

        self.setLayout(layout)
        self.setFixedWidth(self.sizeHint().width() + 50)
        self.setFixedHeight(self.sizeHint().height())

        self.reset_transcriber_controls()

    def get_title(self) -> str:
        if self.file_paths is not None:
            return ", ".join([file_path_as_title(path) for path in self.file_paths])
        if self.url is not None:
            return self.url
        return ""

    def load_preferences(self):
        self.settings.settings.beginGroup("file_transcriber")
        preferences = FileTranscriptionPreferences.load(settings=self.settings.settings)
        self.settings.settings.endGroup()
        return preferences

    def save_preferences(self):
        self.settings.settings.beginGroup("file_transcriber")
        preferences = FileTranscriptionPreferences.from_transcription_options(
            self.transcription_options, self.file_transcription_options
        )
        preferences.save(settings=self.settings.settings)
        self.settings.settings.endGroup()

    def on_click_run(self):
        self.run_button.setDisabled(True)

        model_path = self.transcription_options.model.get_local_model_path()
        if model_path is not None:
            self.on_model_loaded(model_path)
            return

        self.model_loader = ModelDownloader(model=self.transcription_options.model)
        self.model_loader.signals.progress.connect(self.on_download_model_progress)
        self.model_loader.signals.error.connect(self.on_download_model_error)
        self.model_loader.signals.finished.connect(self.on_model_loaded)
        QThreadPool().globalInstance().start(self.model_loader)

    def on_model_loaded(self, model_path: str):
        self.reset_transcriber_controls()

        self.triggered.emit(
            (self.transcription_options, self.file_transcription_options, model_path)
        )
        self.close()

    def on_download_model_progress(self, progress: Tuple[float, float]):
        (current_size, total_size) = progress

        if self.model_download_progress_dialog is None:
            self.model_download_progress_dialog = ModelDownloadProgressDialog(
                model_type=self.transcription_options.model.model_type, parent=self
            )
            self.model_download_progress_dialog.canceled.connect(
                self.on_cancel_model_progress_dialog
            )

        if self.model_download_progress_dialog is not None and total_size > 0:
            self.model_download_progress_dialog.set_value(
                fraction_completed=current_size / total_size
            )

    def on_download_model_error(self, error: str):
        self.reset_model_download()
        show_model_download_error_dialog(self, error)
        self.reset_transcriber_controls()

    def reset_transcriber_controls(self):
        self.run_button.setDisabled(False)

    def on_cancel_model_progress_dialog(self):
        self.reset_transcriber_controls()
        if self.model_loader is not None:
            self.model_loader.cancel()
        self.reset_model_download()

    def reset_model_download(self):
        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.close()
            self.model_download_progress_dialog = None

    def on_word_level_timings_changed(self, value: int):
        self.transcription_options.word_level_timings = (
            value == Qt.CheckState.Checked.value
        )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.model_loader is not None:
            self.model_loader.cancel()
        self.save_preferences()
        super().closeEvent(event)
