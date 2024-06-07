import logging
from typing import Optional
from platformdirs import user_documents_dir

from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool
from PyQt6.QtWidgets import (
    QWidget,
    QFormLayout,
    QPushButton,
    QMessageBox,
    QCheckBox,
    QHBoxLayout,
    QFileDialog
)
from openai import AuthenticationError, OpenAI

from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_password, Key
from buzz.widgets.line_edit import LineEdit
from buzz.widgets.openai_api_key_line_edit import OpenAIAPIKeyLineEdit
from buzz.locale import _


class GeneralPreferencesWidget(QWidget):
    openai_api_key_changed = pyqtSignal(str)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.settings = Settings()

        self.openai_api_key = get_password(Key.OPENAI_API_KEY)

        layout = QFormLayout(self)

        self.openai_api_key_line_edit = OpenAIAPIKeyLineEdit(self.openai_api_key, self)
        self.openai_api_key_line_edit.key_changed.connect(
            self.on_openai_api_key_changed
        )

        self.test_openai_api_key_button = QPushButton(_("Test"))
        self.test_openai_api_key_button.clicked.connect(
            self.on_click_test_openai_api_key_button
        )
        self.update_test_openai_api_key_button()

        layout.addRow(_("OpenAI API key"), self.openai_api_key_line_edit)
        layout.addRow("", self.test_openai_api_key_button)

        self.custom_openai_base_url = self.settings.value(
            key=Settings.Key.CUSTOM_OPENAI_BASE_URL, default_value=""
        )

        self.custom_openai_base_url_line_edit = LineEdit(self.custom_openai_base_url, self)
        self.custom_openai_base_url_line_edit.textChanged.connect(
            self.on_custom_openai_base_url_changed
        )
        self.custom_openai_base_url_line_edit.setMinimumWidth(200)
        self.custom_openai_base_url_line_edit.setPlaceholderText("https://api.openai.com/v1")
        layout.addRow(_("OpenAI base url"), self.custom_openai_base_url_line_edit)

        default_export_file_name = self.settings.get_default_export_file_template()

        default_export_file_name_line_edit = LineEdit(default_export_file_name, self)
        default_export_file_name_line_edit.textChanged.connect(
            self.on_default_export_file_name_changed
        )
        default_export_file_name_line_edit.setMinimumWidth(200)
        layout.addRow(_("Default export file name"), default_export_file_name_line_edit)

        self.recording_export_enabled = self.settings.value(
            key=Settings.Key.RECORDING_TRANSCRIBER_EXPORT_ENABLED, default_value=False
        )

        self.export_enabled_checkbox = QCheckBox(_("Enable live recording transcription export"))
        self.export_enabled_checkbox.setChecked(self.recording_export_enabled)
        self.export_enabled_checkbox.setObjectName("EnableRecordingExportCheckbox")
        self.export_enabled_checkbox.stateChanged.connect(self.on_recording_export_enable_changed)
        layout.addRow("", self.export_enabled_checkbox)

        self.recording_export_folder_browse_button = QPushButton(_("Browse"))
        self.recording_export_folder_browse_button.clicked.connect(self.on_click_browse_export_folder)
        self.recording_export_folder_browse_button.setObjectName("RecordingExportFolderBrowseButton")

        recording_export_folder = self.settings.value(
            key=Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FOLDER, default_value=user_documents_dir()
        )

        recording_export_folder_row = QHBoxLayout()
        self.recording_export_folder_line_edit = LineEdit(recording_export_folder, self)
        self.recording_export_folder_line_edit.textChanged.connect(self.on_recording_export_folder_changed)
        self.recording_export_folder_line_edit.setObjectName("RecordingExportFolderLineEdit")

        self.recording_export_folder_line_edit.setEnabled(self.recording_export_enabled)
        self.recording_export_folder_browse_button.setEnabled(self.recording_export_enabled)

        recording_export_folder_row.addWidget(self.recording_export_folder_line_edit)
        recording_export_folder_row.addWidget(self.recording_export_folder_browse_button)

        layout.addRow(_("Export folder"), recording_export_folder_row)

        self.setLayout(layout)

    def on_default_export_file_name_changed(self, text: str):
        self.settings.set_value(Settings.Key.DEFAULT_EXPORT_FILE_NAME, text)

    def update_test_openai_api_key_button(self):
        self.test_openai_api_key_button.setEnabled(len(self.openai_api_key) > 0)

    def on_click_test_openai_api_key_button(self):
        self.test_openai_api_key_button.setEnabled(False)

        job = TestOpenAIApiKeyJob(api_key=self.openai_api_key)
        job.signals.success.connect(self.on_test_openai_api_key_success)
        job.signals.failed.connect(self.on_test_openai_api_key_failure)
        job.setAutoDelete(True)

        thread_pool = QThreadPool.globalInstance()
        thread_pool.start(job)

    def on_test_openai_api_key_success(self):
        self.test_openai_api_key_button.setEnabled(True)
        QMessageBox.information(
            self,
            _("OpenAI API Key Test"),
            _("Your API key is valid. Buzz will use this key to perform Whisper API transcriptions."),
        )

    def on_test_openai_api_key_failure(self, error: str):
        self.test_openai_api_key_button.setEnabled(True)
        QMessageBox.warning(self, _("OpenAI API Key Test"), error)

    def on_openai_api_key_changed(self, key: str):
        self.openai_api_key = key
        self.update_test_openai_api_key_button()
        self.openai_api_key_changed.emit(key)

    def on_custom_openai_base_url_changed(self, text: str):
        self.settings.set_value(Settings.Key.CUSTOM_OPENAI_BASE_URL, text)

    def on_recording_export_enable_changed(self, state: int):
        self.recording_export_enabled = state == 2

        self.recording_export_folder_line_edit.setEnabled(self.recording_export_enabled)
        self.recording_export_folder_browse_button.setEnabled(self.recording_export_enabled)

        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_EXPORT_ENABLED,
            self.recording_export_enabled,
        )

    def on_click_browse_export_folder(self):
        folder = QFileDialog.getExistingDirectory(self, _("Select Export Folder"))
        self.recording_export_folder_line_edit.setText(folder)
        self.on_recording_export_folder_changed(folder)

    def on_recording_export_folder_changed(self, folder):
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_EXPORT_FOLDER,
            folder,
        )


class TestOpenAIApiKeyJob(QRunnable):
    class Signals(QObject):
        success = pyqtSignal()
        failed = pyqtSignal(str)

    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key
        self.signals = self.Signals()

    def run(self):
        try:
            client = OpenAI(api_key=self.api_key)
            client.models.list()
            self.signals.success.emit()
        except AuthenticationError as exc:
            self.signals.failed.emit(exc.body["message"])
