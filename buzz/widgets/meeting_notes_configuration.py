"""Dedicated endpoint-scoped configuration for meeting summaries."""
import hashlib
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
)
from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_secret, set_secret, delete_secret
from buzz.meeting.openai_compatible_provider import OpenAICompatibleProviderConfig


def secret_name(base_url):
    normalized = OpenAICompatibleProviderConfig(base_url.strip(), "validation").base_url
    return (
        "meeting-summary:endpoint:"
        + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    )


class NotesConfiguration:
    def __init__(
        self, settings=None, get=get_secret, set=set_secret, delete=delete_secret
    ):
        self.settings = settings or Settings()
        self.get_secret, self.set_secret, self.delete_secret = get, set, delete

    def values(self):
        return (
            self.settings.value(
                Settings.Key.MEETING_SUMMARY_BASE_URL, "https://api.openai.com/v1"
            ),
            self.settings.value(Settings.Key.MEETING_SUMMARY_MODEL, ""),
            self.settings.value(Settings.Key.MEETING_SUMMARY_TIMEOUT_SECONDS, 120.0),
        )

    def key_for(self, endpoint):
        return self.get_secret(secret_name(endpoint))

    def save(self, endpoint, model, timeout, key):
        config = OpenAICompatibleProviderConfig(
            endpoint.strip(), model.strip(), key.strip() or None, timeout
        )
        name = secret_name(config.base_url)
        if config.api_key is None:
            self.delete_secret(name)
        else:
            self.set_secret(name, config.api_key)
        for setting, value in (
            (Settings.Key.MEETING_SUMMARY_BASE_URL, config.base_url),
            (Settings.Key.MEETING_SUMMARY_MODEL, config.model),
            (Settings.Key.MEETING_SUMMARY_TIMEOUT_SECONDS, config.timeout_seconds),
        ):
            self.settings.set_value(setting, value)

    def provider_config(self):
        endpoint, model, timeout = self.values()
        return OpenAICompatibleProviderConfig(
            endpoint, model, self.key_for(endpoint) or None, timeout
        )


class NotesConfigurationDialog(QDialog):
    def __init__(self, operations, parent=None):
        super().__init__(parent)
        self.operations = operations
        self.setWindowTitle("AI Notes API Configuration")
        layout = QFormLayout(self)
        endpoint, model, timeout = operations.values()
        self.endpoint = QLineEdit(endpoint, self)
        self.model = QLineEdit(model, self)
        self.timeout = QDoubleSpinBox(self)
        self.timeout.setRange(0.1, 86400)
        self.timeout.setValue(timeout)
        self.key = QLineEdit(self)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.message = QLabel(
            "Only transcript text is sent. A blank key sends no Authorization header.",
            self,
        )
        self.message.setWordWrap(True)
        layout.addRow("Base URL", self.endpoint)
        layout.addRow("Model", self.model)
        layout.addRow("Timeout (seconds)", self.timeout)
        layout.addRow("API key", self.key)
        layout.addRow(self.message)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)
        # Every endpoint edit clears the previous credential before attempting a read.
        self.endpoint.textChanged.connect(self.load_key)
        self.load_key()

    def load_key(self):
        self.key.clear()
        try:
            self.key.setText(self.operations.key_for(self.endpoint.text()))
        except Exception:
            self.message.setText("Could not load credentials for this endpoint.")

    def save(self):
        try:
            self.operations.save(
                self.endpoint.text(),
                self.model.text(),
                self.timeout.value(),
                self.key.text(),
            )
        except Exception:
            self.message.setText(
                "Could not save configuration. Check the endpoint, model, timeout, and secret store."
            )
            return
        self.accept()
