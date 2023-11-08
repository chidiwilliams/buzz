import logging
from typing import Optional

import openai
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool
from PyQt6.QtWidgets import QWidget, QFormLayout, QPushButton, QMessageBox
from openai.error import AuthenticationError

from buzz.store.keyring_store import KeyringStore
from buzz.widgets.line_edit import LineEdit
from buzz.widgets.openai_api_key_line_edit import OpenAIAPIKeyLineEdit


class GeneralPreferencesWidget(QWidget):
    openai_api_key_changed = pyqtSignal(str)
    default_export_file_name_changed = pyqtSignal(str)

    def __init__(
        self,
        default_export_file_name: str,
        keyring_store=KeyringStore(),
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.openai_api_key = keyring_store.get_password(
            KeyringStore.Key.OPENAI_API_KEY
        )

        layout = QFormLayout(self)

        self.openai_api_key_line_edit = OpenAIAPIKeyLineEdit(self.openai_api_key, self)
        self.openai_api_key_line_edit.key_changed.connect(
            self.on_openai_api_key_changed
        )

        self.test_openai_api_key_button = QPushButton("Test")
        self.test_openai_api_key_button.clicked.connect(
            self.on_click_test_openai_api_key_button
        )
        self.update_test_openai_api_key_button()

        layout.addRow("OpenAI API Key", self.openai_api_key_line_edit)
        layout.addRow("", self.test_openai_api_key_button)

        default_export_file_name_line_edit = LineEdit(default_export_file_name, self)
        default_export_file_name_line_edit.textChanged.connect(
            self.default_export_file_name_changed
        )
        default_export_file_name_line_edit.setMinimumWidth(200)
        layout.addRow("Default export file name", default_export_file_name_line_edit)

        self.setLayout(layout)

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
            "OpenAI API Key Test",
            "Your API key is valid. Buzz will use this key to perform Whisper API transcriptions.",
        )

    def on_test_openai_api_key_failure(self, error: str):
        self.test_openai_api_key_button.setEnabled(True)
        QMessageBox.warning(self, "OpenAI API Key Test", error)

    def on_openai_api_key_changed(self, key: str):
        self.openai_api_key = key
        self.update_test_openai_api_key_button()
        self.openai_api_key_changed.emit(key)


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
            openai.Model.list(api_key=self.api_key)
            self.signals.success.emit()
        except AuthenticationError as exc:
            logging.error(exc)
            self.signals.failed.emit(str(exc))
