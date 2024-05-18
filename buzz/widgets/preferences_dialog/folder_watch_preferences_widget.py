from typing import Tuple, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QPushButton,
    QFormLayout,
    QHBoxLayout,
    QFileDialog,
    QCheckBox,
    QVBoxLayout,
)

from buzz.locale import _
from buzz.store.keyring_store import Key, get_password
from buzz.transcriber.transcriber import (
    TranscriptionOptions,
    FileTranscriptionOptions,
)
from buzz.widgets.line_edit import LineEdit
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)
from buzz.widgets.preferences_dialog.models.folder_watch_preferences import (
    FolderWatchPreferences,
)
from buzz.widgets.transcriber.file_transcription_form_widget import (
    FileTranscriptionFormWidget,
)


class FolderWatchPreferencesWidget(QWidget):
    config_changed = pyqtSignal(FolderWatchPreferences)

    def __init__(
        self, config: FolderWatchPreferences, parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self.config = config

        checkbox = QCheckBox(_("Enable folder watch"))
        checkbox.setChecked(config.enabled)
        checkbox.setObjectName("EnableFolderWatchCheckbox")
        checkbox.stateChanged.connect(self.on_enable_changed)

        input_folder_browse_button = QPushButton(_("Browse"))
        input_folder_browse_button.clicked.connect(self.on_click_browse_input_folder)

        output_folder_browse_button = QPushButton(_("Browse"))
        output_folder_browse_button.clicked.connect(self.on_click_browse_output_folder)

        input_folder_row = QHBoxLayout()
        self.input_folder_line_edit = LineEdit(config.input_directory, self)
        self.input_folder_line_edit.setPlaceholderText("/path/to/input/folder")
        self.input_folder_line_edit.textChanged.connect(self.on_input_folder_changed)
        self.input_folder_line_edit.setObjectName("InputFolderLineEdit")

        input_folder_row.addWidget(self.input_folder_line_edit)
        input_folder_row.addWidget(input_folder_browse_button)

        output_folder_row = QHBoxLayout()
        self.output_folder_line_edit = LineEdit(config.output_directory, self)
        self.output_folder_line_edit.setPlaceholderText("/path/to/output/folder")
        self.output_folder_line_edit.textChanged.connect(self.on_output_folder_changed)
        self.output_folder_line_edit.setObjectName("OutputFolderLineEdit")

        output_folder_row.addWidget(self.output_folder_line_edit)
        output_folder_row.addWidget(output_folder_browse_button)

        openai_access_token = get_password(Key.OPENAI_API_KEY)
        (
            transcription_options,
            file_transcription_options,
        ) = config.file_transcription_options.to_transcription_options(
            openai_access_token=openai_access_token,
            file_paths=[],
        )

        transcription_form_widget = FileTranscriptionFormWidget(
            transcription_options=transcription_options,
            file_transcription_options=file_transcription_options,
            parent=self,
        )
        transcription_form_widget.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        layout = QVBoxLayout(self)

        folders_form_layout = QFormLayout()

        folders_form_layout.addRow("", checkbox)
        folders_form_layout.addRow(_("Input folder"), input_folder_row)
        folders_form_layout.addRow(_("Output folder"), output_folder_row)
        folders_form_layout.addWidget(transcription_form_widget)

        layout.addLayout(folders_form_layout)
        layout.addWidget(transcription_form_widget)
        layout.addStretch()

        self.setLayout(layout)

    def on_click_browse_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, _("Select Input Folder"))
        self.input_folder_line_edit.setText(folder)
        self.on_input_folder_changed(folder)

    def on_input_folder_changed(self, folder):
        self.config.input_directory = folder
        self.config_changed.emit(self.config)

    def on_click_browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, _("Select Output Folder"))
        self.output_folder_line_edit.setText(folder)
        self.on_output_folder_changed(folder)

    def on_output_folder_changed(self, folder):
        self.config.output_directory = folder
        self.config_changed.emit(self.config)

    def on_enable_changed(self, state: int):
        self.config.enabled = state == 2
        self.config_changed.emit(self.config)

    def on_transcription_options_changed(
        self, options: Tuple[TranscriptionOptions, FileTranscriptionOptions]
    ):
        transcription_options, file_transcription_options = options
        self.config.file_transcription_options = (
            FileTranscriptionPreferences.from_transcription_options(
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
            )
        )
        self.config_changed.emit(self.config)
