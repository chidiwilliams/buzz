import logging
from typing import Optional

import openai
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool
from PyQt6.QtWidgets import QWidget, QFormLayout, QLineEdit, QPushButton, QMessageBox
from openai.error import AuthenticationError

from buzz.widgets.openai_api_key_line_edit import OpenAIAPIKeyLineEdit


class GeneralPreferencesWidget(QWidget):
    openai_api_key_changed = pyqtSignal(str)

    def __init__(self, openai_api_key: str, parent=Optional[QWidget]):
        super().__init__(parent)
        self.openai_api_key = openai_api_key

        layout = QFormLayout(self)

        self.openai_api_key_line_edit = OpenAIAPIKeyLineEdit(openai_api_key, self)
        self.openai_api_key_line_edit.key_changed.connect(self.on_openai_api_key_changed)

        self.test_openai_api_key_button = QPushButton('Test')
        self.test_openai_api_key_button.clicked.connect(self.on_click_test_openai_api_key_button)

        layout.addRow('OpenAI API Key', self.openai_api_key_line_edit)
        layout.addRow('', self.test_openai_api_key_button)

        self.setLayout(layout)

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
        QMessageBox.information(self, 'OpenAI API Key Test',
                                'Your API key is valid. Buzz will use this key to perform Whisper API transcriptions.')

    def on_test_openai_api_key_failure(self, error: str):
        self.test_openai_api_key_button.setEnabled(True)
        QMessageBox.warning(self, 'OpenAI API Key Test', error)

    def on_toggle_show_action_triggered(self):
        if self.openai_api_key_line_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.openai_api_key_line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.openai_api_key_line_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def on_openai_api_key_changed(self, key: str):
        self.openai_api_key = key
        self.test_openai_api_key_button.setEnabled(len(key) > 0)
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
