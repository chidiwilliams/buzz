from typing import Optional, List, Tuple

from PyQt6 import QtGui
from PyQt6.QtCore import pyqtSignal, Qt, QThreadPool
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
)

from buzz.dialogs import show_model_download_error_dialog
from buzz.locale import _
from buzz.model_loader import ModelDownloader, TranscriptionModel, ModelType
from buzz.paths import file_paths_as_title
from buzz.settings.settings import Settings
from buzz.store.keyring_store import KeyringStore
from buzz.transcriber import (
    FileTranscriptionOptions,
    TranscriptionOptions,
    Task,
    DEFAULT_WHISPER_TEMPERATURE,
    OutputFormat,
)
from buzz.widgets.model_download_progress_dialog import ModelDownloadProgressDialog
from buzz.widgets.transcriber.transcription_options_group_box import (
    TranscriptionOptionsGroupBox,
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
        file_paths: List[str],
        default_output_file_name: str,
        parent: Optional[QWidget] = None,
        flags: Qt.WindowType = Qt.WindowType.Widget,
    ) -> None:
        super().__init__(parent, flags)

        self.setWindowTitle(file_paths_as_title(file_paths))

        openai_access_token = KeyringStore().get_password(
            KeyringStore.Key.OPENAI_API_KEY
        )

        self.file_paths = file_paths
        default_language = self.settings.value(
            key=Settings.Key.FILE_TRANSCRIBER_LANGUAGE, default_value=""
        )
        self.transcription_options = TranscriptionOptions(
            openai_access_token=openai_access_token,
            model=self.settings.value(
                key=Settings.Key.FILE_TRANSCRIBER_MODEL,
                default_value=TranscriptionModel(),
            ),
            task=self.settings.value(
                key=Settings.Key.FILE_TRANSCRIBER_TASK, default_value=Task.TRANSCRIBE
            ),
            language=default_language if default_language != "" else None,
            initial_prompt=self.settings.value(
                key=Settings.Key.FILE_TRANSCRIBER_INITIAL_PROMPT, default_value=""
            ),
            temperature=self.settings.value(
                key=Settings.Key.FILE_TRANSCRIBER_TEMPERATURE,
                default_value=DEFAULT_WHISPER_TEMPERATURE,
            ),
            word_level_timings=self.settings.value(
                key=Settings.Key.FILE_TRANSCRIBER_WORD_LEVEL_TIMINGS,
                default_value=False,
            ),
        )
        default_export_format_states: List[str] = self.settings.value(
            key=Settings.Key.FILE_TRANSCRIBER_EXPORT_FORMATS, default_value=[]
        )
        self.file_transcription_options = FileTranscriptionOptions(
            file_paths=self.file_paths,
            output_formats=set(
                [
                    OutputFormat(output_format)
                    for output_format in default_export_format_states
                ]
            ),
            default_output_file_name=default_output_file_name,
        )

        layout = QVBoxLayout(self)

        transcription_options_group_box = TranscriptionOptionsGroupBox(
            default_transcription_options=self.transcription_options, parent=self
        )
        transcription_options_group_box.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        self.word_level_timings_checkbox = QCheckBox(_("Word-level timings"))
        self.word_level_timings_checkbox.setChecked(
            self.settings.value(
                key=Settings.Key.FILE_TRANSCRIBER_WORD_LEVEL_TIMINGS,
                default_value=False,
            )
        )
        self.word_level_timings_checkbox.stateChanged.connect(
            self.on_word_level_timings_changed
        )

        file_transcription_layout = QFormLayout()
        file_transcription_layout.addRow("", self.word_level_timings_checkbox)

        export_format_layout = QHBoxLayout()
        for output_format in OutputFormat:
            export_format_checkbox = QCheckBox(
                f"{output_format.value.upper()}", parent=self
            )
            export_format_checkbox.setChecked(
                output_format in self.file_transcription_options.output_formats
            )
            export_format_checkbox.stateChanged.connect(
                self.get_on_checkbox_state_changed_callback(output_format)
            )
            export_format_layout.addWidget(export_format_checkbox)

        file_transcription_layout.addRow("Export:", export_format_layout)

        self.run_button = QPushButton(_("Run"), self)
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.on_click_run)

        layout.addWidget(transcription_options_group_box)
        layout.addLayout(file_transcription_layout)
        layout.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignRight)

        self.setLayout(layout)
        self.setFixedSize(self.sizeHint())

    def get_on_checkbox_state_changed_callback(self, output_format: OutputFormat):
        def on_checkbox_state_changed(state: int):
            if state == Qt.CheckState.Checked.value:
                self.file_transcription_options.output_formats.add(output_format)
            elif state == Qt.CheckState.Unchecked.value:
                self.file_transcription_options.output_formats.remove(output_format)

        return on_checkbox_state_changed

    def on_transcription_options_changed(
        self, transcription_options: TranscriptionOptions
    ):
        self.transcription_options = transcription_options
        self.word_level_timings_checkbox.setDisabled(
            self.transcription_options.model.model_type == ModelType.HUGGING_FACE
            or self.transcription_options.model.model_type
            == ModelType.OPEN_AI_WHISPER_API
        )
        if self.transcription_options.openai_access_token != "":
            self.openai_access_token_changed.emit(
                self.transcription_options.openai_access_token
            )

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

        if self.model_download_progress_dialog is not None:
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

        self.settings.set_value(
            Settings.Key.FILE_TRANSCRIBER_LANGUAGE, self.transcription_options.language
        )
        self.settings.set_value(
            Settings.Key.FILE_TRANSCRIBER_TASK, self.transcription_options.task
        )
        self.settings.set_value(
            Settings.Key.FILE_TRANSCRIBER_TEMPERATURE,
            self.transcription_options.temperature,
        )
        self.settings.set_value(
            Settings.Key.FILE_TRANSCRIBER_INITIAL_PROMPT,
            self.transcription_options.initial_prompt,
        )
        self.settings.set_value(
            Settings.Key.FILE_TRANSCRIBER_MODEL, self.transcription_options.model
        )
        self.settings.set_value(
            key=Settings.Key.FILE_TRANSCRIBER_WORD_LEVEL_TIMINGS,
            value=self.transcription_options.word_level_timings,
        )
        self.settings.set_value(
            key=Settings.Key.FILE_TRANSCRIBER_EXPORT_FORMATS,
            value=[
                export_format.value
                for export_format in self.file_transcription_options.output_formats
            ],
        )

        super().closeEvent(event)
