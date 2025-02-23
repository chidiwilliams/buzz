import re
import logging
import requests
from typing import Optional
from platformdirs import user_documents_dir

from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool, QLocale
from PyQt6.QtWidgets import (
    QWidget,
    QFormLayout,
    QPushButton,
    QMessageBox,
    QCheckBox,
    QHBoxLayout,
    QFileDialog,
    QSpinBox,
    QComboBox,
    QLabel,
    QSizePolicy,
)
from PyQt6.QtGui import QIcon
from openai import AuthenticationError, OpenAI

from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_password, Key
from buzz.widgets.line_edit import LineEdit
from buzz.widgets.openai_api_key_line_edit import OpenAIAPIKeyLineEdit
from buzz.locale import _
from buzz.widgets.icon import INFO_ICON_PATH
from buzz.settings.recording_transcriber_mode import RecordingTranscriberMode

BASE64_PATTERN = re.compile(r'^[A-Za-z0-9+/=_-]*$')

ui_locales = {
    "en_US": _("English"),
    "ca_ES": _("Catalan"),
    "da_DK": _("Danish"),
    "es_ES": _("Spanish"),
    "it_IT": _("Italian"),
    "ja_JP": _("Japanese"),
    "lv_LV": _("Latvian"),
    "pl_PL": _("Polish"),
    "uk_UA": _("Ukrainian"),
    "zh_CN": _("Chinese (Simplified)"),
    "zh_TW": _("Chinese (Traditional)")
}


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

        self.ui_language_combo_box = QComboBox(self)
        self.ui_language_combo_box.addItems(ui_locales.values())
        system_locale = self.settings.value(Settings.Key.UI_LOCALE, QLocale().name())
        locale_index = 0
        for i, (code, language) in enumerate(ui_locales.items()):
            if code == system_locale:
                locale_index = i
                break
        self.ui_language_combo_box.setCurrentIndex(locale_index)
        self.ui_language_combo_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.ui_language_combo_box.currentIndexChanged.connect(self.on_language_changed)

        self.ui_locale_layout = QHBoxLayout()
        self.ui_locale_layout.setContentsMargins(0, 0, 0, 0)
        self.ui_locale_layout.setSpacing(0)
        self.ui_locale_layout.addWidget(self.ui_language_combo_box)

        self.load_note_tooltip_icon = QLabel()
        self.load_note_tooltip_icon.setPixmap(QIcon(INFO_ICON_PATH).pixmap(23, 23))
        self.load_note_tooltip_icon.setToolTip(_("Restart required!"))
        self.load_note_tooltip_icon.setVisible(False)
        self.ui_locale_layout.addWidget(self.load_note_tooltip_icon)

        layout.addRow(_("Ui Language"), self.ui_locale_layout)

        self.font_size_spin_box = QSpinBox(self)
        self.font_size_spin_box.setMinimum(8)
        self.font_size_spin_box.setMaximum(32)
        self.font_size_spin_box.setValue(self.font().pointSize())
        self.font_size_spin_box.valueChanged.connect(self.on_font_size_changed)

        layout.addRow(_("Font Size"), self.font_size_spin_box)

        self.openai_api_key_line_edit = OpenAIAPIKeyLineEdit(self.openai_api_key, self)
        self.openai_api_key_line_edit.key_changed.connect(
            self.on_openai_api_key_changed
        )
        self.openai_api_key_line_edit.focus_out.connect(self.on_openai_api_key_focus_out)
        self.openai_api_key_line_edit.setMinimumWidth(200)

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

        self.recording_transcriber_mode = QComboBox(self)
        for mode in RecordingTranscriberMode:
            self.recording_transcriber_mode.addItem(mode.value)

        self.recording_transcriber_mode.setCurrentIndex(
            self.settings.value(Settings.Key.RECORDING_TRANSCRIBER_MODE, 0)
        )
        self.recording_transcriber_mode.currentIndexChanged.connect(self.on_recording_transcriber_mode_changed)

        layout.addRow(_("Live recording mode"), self.recording_transcriber_mode)

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
            _("Your API key is valid. Buzz will use this key to perform Whisper API transcriptions and AI translations."),
        )

    def on_test_openai_api_key_failure(self, error: str):
        self.test_openai_api_key_button.setEnabled(True)
        QMessageBox.warning(self, _("OpenAI API Key Test"), error)

    def on_openai_api_key_changed(self, key: str):
        self.openai_api_key = key
        self.update_test_openai_api_key_button()
        self.openai_api_key_changed.emit(key)

    def on_openai_api_key_focus_out(self):
        if not BASE64_PATTERN.match(self.openai_api_key):
            QMessageBox.warning(
                self,
                _("Invalid API key"),
                _("API supports only base64 characters (A-Za-z0-9+/=_-). Other characters in API key may cause errors."),
            )

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

    def on_language_changed(self, index):
        selected_language = self.ui_language_combo_box.itemText(index)
        locale_code = next((code for code, lang in ui_locales.items() if lang == selected_language), "en_US")

        self.load_note_tooltip_icon.setVisible(True)

        self.settings.set_value(Settings.Key.UI_LOCALE, locale_code)

    def on_font_size_changed(self, value):
        from buzz.widgets.application import Application
        font = self.font()
        font.setPointSize(value)
        self.setFont(font)
        Application.instance().setFont(font)

        self.settings.set_value(Settings.Key.FONT_SIZE, value)

    def on_recording_transcriber_mode_changed(self, value):
        self.settings.set_value(Settings.Key.RECORDING_TRANSCRIBER_MODE, value)

class TestOpenAIApiKeyJob(QRunnable):
    class Signals(QObject):
        success = pyqtSignal()
        failed = pyqtSignal(str)

    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key
        self.signals = self.Signals()

    def run(self):
        settings = Settings()
        custom_openai_base_url = settings.value(
            key=Settings.Key.CUSTOM_OPENAI_BASE_URL, default_value=""
        )

        if custom_openai_base_url:
            try:
                if not custom_openai_base_url.endswith("/"):
                    custom_openai_base_url += "/"

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                response = requests.get(custom_openai_base_url + "models", headers=headers, timeout=5)

                if response.status_code != 200:
                    self.signals.failed.emit(
                        _("OpenAI API returned invalid response. Please check the API url or your key. "
                          "Transcription and translation may still work if the API does not support key validation.")
                    )
                    return
            except requests.exceptions.RequestException as exc:
                self.signals.failed.emit(str(exc))
                return

        try:
            client = OpenAI(
                api_key=self.api_key,
                base_url=custom_openai_base_url if custom_openai_base_url else None,
                timeout=5,
            )
            client.models.list()
            self.signals.success.emit()
        except AuthenticationError as exc:
            self.signals.failed.emit(exc.body["message"])
