import enum
import sys
from enum import auto
from typing import Dict, List, Optional, Tuple

import sounddevice
from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QModelIndex, QThreadPool
from PyQt6.QtGui import QCloseEvent, QIcon, QKeySequence, QTextCursor, QPainter, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFormLayout,
    QSizePolicy,
)

from buzz.cache import TasksCache
from .__version__ import VERSION
from .action import Action
from .assets import get_asset_path
from .dialogs import show_model_download_error_dialog
from .widgets.icon import Icon, BUZZ_ICON_PATH
from .locale import _
from .model_loader import (
    WhisperModelSize,
    ModelType,
    TranscriptionModel,
    ModelDownloader,
)
from .recording import RecordingAmplitudeListener
from .settings.settings import Settings, APP_NAME
from .settings.shortcut import Shortcut
from .settings.shortcut_settings import ShortcutSettings
from .store.keyring_store import KeyringStore
from .transcriber import (
    SUPPORTED_OUTPUT_FORMATS,
    FileTranscriptionOptions,
    Task,
    TranscriptionOptions,
    FileTranscriptionTask,
    LOADED_WHISPER_DLL,
    DEFAULT_WHISPER_TEMPERATURE,
)
from .recording_transcriber import RecordingTranscriber
from .file_transcriber_queue_worker import FileTranscriberQueueWorker
from .widgets.menu_bar import MenuBar
from .widgets.model_download_progress_dialog import ModelDownloadProgressDialog
from .widgets.toolbar import ToolBar
from .widgets.transcriber.file_transcriber_widget import FileTranscriberWidget
from .widgets.transcriber.transcription_options_group_box import (
    TranscriptionOptionsGroupBox,
)
from .widgets.transcription_tasks_table_widget import TranscriptionTasksTableWidget
from .widgets.transcription_viewer_widget import TranscriptionViewerWidget


class FormLabel(QLabel):
    def __init__(self, name: str, parent: Optional[QWidget], *args) -> None:
        super().__init__(name, parent, *args)
        self.setStyleSheet("QLabel { text-align: right; }")
        self.setAlignment(
            Qt.AlignmentFlag(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            )
        )


class AudioDevicesComboBox(QComboBox):
    """AudioDevicesComboBox displays a list of available audio input devices"""

    device_changed = pyqtSignal(int)
    audio_devices: List[Tuple[int, str]]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.audio_devices = self.get_audio_devices()
        self.addItems([device[1] for device in self.audio_devices])
        self.currentIndexChanged.connect(self.on_index_changed)

        default_device_id = self.get_default_device_id()
        if default_device_id != -1:
            for i, device in enumerate(self.audio_devices):
                if device[0] == default_device_id:
                    self.setCurrentIndex(i)

    def get_audio_devices(self) -> List[Tuple[int, str]]:
        try:
            devices: sounddevice.DeviceList = sounddevice.query_devices()
            return [
                (device.get("index"), device.get("name"))
                for device in devices
                if device.get("max_input_channels") > 0
            ]
        except UnicodeDecodeError:
            QMessageBox.critical(
                self,
                "",
                "An error occurred while loading your audio devices. Please check the application logs for more "
                "information.",
            )
            return []

    def on_index_changed(self, index: int):
        self.device_changed.emit(self.audio_devices[index][0])

    def get_default_device_id(self) -> Optional[int]:
        default_system_device = sounddevice.default.device[0]
        if default_system_device != -1:
            return default_system_device

        audio_devices = self.get_audio_devices()
        if len(audio_devices) > 0:
            return audio_devices[0][0]

        return -1


class TextDisplayBox(QPlainTextEdit):
    """TextDisplayBox is a read-only textbox"""

    def __init__(self, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.setReadOnly(True)


class RecordButton(QPushButton):
    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__(_("Record"), parent)
        self.setDefault(True)
        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        )

    def set_stopped(self):
        self.setText(_("Record"))
        self.setDefault(True)

    def set_recording(self):
        self.setText(_("Stop"))
        self.setDefault(False)


class AudioMeterWidget(QWidget):
    current_amplitude: float
    BAR_WIDTH = 2
    BAR_MARGIN = 1
    BAR_INACTIVE_COLOR: QColor
    BAR_ACTIVE_COLOR: QColor

    # Factor by which the amplitude is scaled to make the changes more visible
    DIFF_MULTIPLIER_FACTOR = 10
    SMOOTHING_FACTOR = 0.95

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumWidth(10)
        self.setFixedHeight(16)

        # Extra padding to fix layout
        self.PADDING_TOP = 3

        self.current_amplitude = 0.0

        self.MINIMUM_AMPLITUDE = 0.00005  # minimum amplitude to show the first bar
        self.AMPLITUDE_SCALE_FACTOR = 15  # scale the amplitudes such that 1/AMPLITUDE_SCALE_FACTOR will show all bars

        if self.palette().window().color().black() > 127:
            self.BAR_INACTIVE_COLOR = QColor("#555")
            self.BAR_ACTIVE_COLOR = QColor("#999")
        else:
            self.BAR_INACTIVE_COLOR = QColor("#BBB")
            self.BAR_ACTIVE_COLOR = QColor("#555")

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)

        rect = self.rect()
        center_x = rect.center().x()
        num_bars_in_half = int((rect.width() / 2) / (self.BAR_MARGIN + self.BAR_WIDTH))
        for i in range(num_bars_in_half):
            is_bar_active = (
                (self.current_amplitude - self.MINIMUM_AMPLITUDE)
                * self.AMPLITUDE_SCALE_FACTOR
            ) > (i / num_bars_in_half)
            painter.setBrush(
                self.BAR_ACTIVE_COLOR if is_bar_active else self.BAR_INACTIVE_COLOR
            )

            # draw to left
            painter.drawRect(
                center_x - ((i + 1) * (self.BAR_MARGIN + self.BAR_WIDTH)),
                rect.top() + self.PADDING_TOP,
                self.BAR_WIDTH,
                rect.height() - self.PADDING_TOP,
            )
            # draw to right
            painter.drawRect(
                center_x + (self.BAR_MARGIN + (i * (self.BAR_MARGIN + self.BAR_WIDTH))),
                rect.top() + self.PADDING_TOP,
                self.BAR_WIDTH,
                rect.height() - self.PADDING_TOP,
            )

    def update_amplitude(self, amplitude: float):
        self.current_amplitude = max(
            amplitude, self.current_amplitude * self.SMOOTHING_FACTOR
        )
        self.repaint()


class RecordingTranscriberWidget(QWidget):
    current_status: "RecordingStatus"
    transcription_options: TranscriptionOptions
    selected_device_id: Optional[int]
    model_download_progress_dialog: Optional[ModelDownloadProgressDialog] = None
    transcriber: Optional[RecordingTranscriber] = None
    model_loader: Optional[ModelDownloader] = None
    transcription_thread: Optional[QThread] = None
    recording_amplitude_listener: Optional[RecordingAmplitudeListener] = None
    device_sample_rate: Optional[int] = None

    class RecordingStatus(enum.Enum):
        STOPPED = auto()
        RECORDING = auto()

    def __init__(
        self, parent: Optional[QWidget] = None, flags: Optional[Qt.WindowType] = None
    ) -> None:
        super().__init__(parent)

        if flags is not None:
            self.setWindowFlags(flags)

        layout = QVBoxLayout(self)

        self.current_status = self.RecordingStatus.STOPPED
        self.setWindowTitle(_("Live Recording"))

        self.settings = Settings()
        default_language = self.settings.value(
            key=Settings.Key.RECORDING_TRANSCRIBER_LANGUAGE, default_value=""
        )
        self.transcription_options = TranscriptionOptions(
            model=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_MODEL,
                default_value=TranscriptionModel(
                    model_type=ModelType.WHISPER_CPP
                    if LOADED_WHISPER_DLL
                    else ModelType.WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
            ),
            task=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_TASK,
                default_value=Task.TRANSCRIBE,
            ),
            language=default_language if default_language != "" else None,
            initial_prompt=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_INITIAL_PROMPT, default_value=""
            ),
            temperature=self.settings.value(
                key=Settings.Key.RECORDING_TRANSCRIBER_TEMPERATURE,
                default_value=DEFAULT_WHISPER_TEMPERATURE,
            ),
            word_level_timings=False,
        )

        self.audio_devices_combo_box = AudioDevicesComboBox(self)
        self.audio_devices_combo_box.device_changed.connect(self.on_device_changed)
        self.selected_device_id = self.audio_devices_combo_box.get_default_device_id()

        self.record_button = RecordButton(self)
        self.record_button.clicked.connect(self.on_record_button_clicked)

        self.text_box = TextDisplayBox(self)
        self.text_box.setPlaceholderText(_("Click Record to begin..."))

        transcription_options_group_box = TranscriptionOptionsGroupBox(
            default_transcription_options=self.transcription_options,
            # Live transcription with OpenAI Whisper API not implemented
            model_types=[
                model_type
                for model_type in ModelType
                if model_type is not ModelType.OPEN_AI_WHISPER_API
            ],
            parent=self,
        )
        transcription_options_group_box.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        recording_options_layout = QFormLayout()
        recording_options_layout.addRow(_("Microphone:"), self.audio_devices_combo_box)

        self.audio_meter_widget = AudioMeterWidget(self)

        record_button_layout = QHBoxLayout()
        record_button_layout.addWidget(self.audio_meter_widget)
        record_button_layout.addWidget(self.record_button)

        layout.addWidget(transcription_options_group_box)
        layout.addLayout(recording_options_layout)
        layout.addLayout(record_button_layout)
        layout.addWidget(self.text_box)

        self.setLayout(layout)
        self.setFixedSize(self.sizeHint())

        self.reset_recording_amplitude_listener()

    def on_transcription_options_changed(
        self, transcription_options: TranscriptionOptions
    ):
        self.transcription_options = transcription_options

    def on_device_changed(self, device_id: int):
        self.selected_device_id = device_id
        self.reset_recording_amplitude_listener()

    def reset_recording_amplitude_listener(self):
        if self.recording_amplitude_listener is not None:
            self.recording_amplitude_listener.stop_recording()

        # Listening to audio will fail if there are no input devices
        if self.selected_device_id is None or self.selected_device_id == -1:
            return

        # Get the device sample rate before starting the listener as the PortAudio function
        # fails if you try to get the device's settings while recording is in progress.
        self.device_sample_rate = RecordingTranscriber.get_device_sample_rate(
            self.selected_device_id
        )

        self.recording_amplitude_listener = RecordingAmplitudeListener(
            input_device_index=self.selected_device_id, parent=self
        )
        self.recording_amplitude_listener.amplitude_changed.connect(
            self.on_recording_amplitude_changed
        )
        self.recording_amplitude_listener.start_recording()

    def on_record_button_clicked(self):
        if self.current_status == self.RecordingStatus.STOPPED:
            self.start_recording()
            self.current_status = self.RecordingStatus.RECORDING
            self.record_button.set_recording()
        else:  # RecordingStatus.RECORDING
            self.stop_recording()
            self.set_recording_status_stopped()

    def start_recording(self):
        self.record_button.setDisabled(True)

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
        self.reset_recording_controls()
        self.model_loader = None

        self.transcription_thread = QThread()

        # TODO: make runnable
        self.transcriber = RecordingTranscriber(
            input_device_index=self.selected_device_id,
            sample_rate=self.device_sample_rate,
            transcription_options=self.transcription_options,
            model_path=model_path,
        )

        self.transcriber.moveToThread(self.transcription_thread)

        self.transcription_thread.started.connect(self.transcriber.start)
        self.transcription_thread.finished.connect(
            self.transcription_thread.deleteLater
        )

        self.transcriber.transcription.connect(self.on_next_transcription)

        self.transcriber.finished.connect(self.on_transcriber_finished)
        self.transcriber.finished.connect(self.transcription_thread.quit)
        self.transcriber.finished.connect(self.transcriber.deleteLater)

        self.transcriber.error.connect(self.on_transcriber_error)
        self.transcriber.error.connect(self.transcription_thread.quit)
        self.transcriber.error.connect(self.transcriber.deleteLater)

        self.transcription_thread.start()

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

    def set_recording_status_stopped(self):
        self.record_button.set_stopped()
        self.current_status = self.RecordingStatus.STOPPED

    def on_download_model_error(self, error: str):
        self.reset_model_download()
        show_model_download_error_dialog(self, error)
        self.stop_recording()
        self.set_recording_status_stopped()
        self.record_button.setDisabled(False)

    def on_next_transcription(self, text: str):
        text = text.strip()
        if len(text) > 0:
            self.text_box.moveCursor(QTextCursor.MoveOperation.End)
            if len(self.text_box.toPlainText()) > 0:
                self.text_box.insertPlainText("\n\n")
            self.text_box.insertPlainText(text)
            self.text_box.moveCursor(QTextCursor.MoveOperation.End)

    def stop_recording(self):
        if self.transcriber is not None:
            self.transcriber.stop_recording()
        # Disable record button until the transcription is actually stopped in the background
        self.record_button.setDisabled(True)

    def on_transcriber_finished(self):
        self.reset_record_button()

    def on_transcriber_error(self, error: str):
        self.reset_record_button()
        self.set_recording_status_stopped()
        QMessageBox.critical(
            self,
            "",
            _("An error occurred while starting a new recording:")
            + error
            + ". "
            + _(
                "Please check your audio devices or check the application logs for more information."
            ),
        )

    def on_cancel_model_progress_dialog(self):
        if self.model_loader is not None:
            self.model_loader.cancel()
        self.reset_model_download()
        self.set_recording_status_stopped()
        self.record_button.setDisabled(False)

    def reset_model_download(self):
        if self.model_download_progress_dialog is not None:
            self.model_download_progress_dialog.close()
            self.model_download_progress_dialog = None

    def reset_recording_controls(self):
        # Clear text box placeholder because the first chunk takes a while to process
        self.text_box.setPlaceholderText("")
        self.reset_record_button()
        self.reset_model_download()

    def reset_record_button(self):
        self.record_button.setEnabled(True)

    def on_recording_amplitude_changed(self, amplitude: float):
        self.audio_meter_widget.update_amplitude(amplitude)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.model_loader is not None:
            self.model_loader.cancel()

        self.stop_recording()
        if self.recording_amplitude_listener is not None:
            self.recording_amplitude_listener.stop_recording()
            self.recording_amplitude_listener.deleteLater()

        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_LANGUAGE,
            self.transcription_options.language,
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_TASK, self.transcription_options.task
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_TEMPERATURE,
            self.transcription_options.temperature,
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_INITIAL_PROMPT,
            self.transcription_options.initial_prompt,
        )
        self.settings.set_value(
            Settings.Key.RECORDING_TRANSCRIBER_MODEL, self.transcription_options.model
        )

        return super().closeEvent(event)


RECORD_ICON_PATH = get_asset_path("assets/mic_FILL0_wght700_GRAD0_opsz48.svg")
EXPAND_ICON_PATH = get_asset_path("assets/open_in_full_FILL0_wght700_GRAD0_opsz48.svg")
ADD_ICON_PATH = get_asset_path("assets/add_FILL0_wght700_GRAD0_opsz48.svg")
TRASH_ICON_PATH = get_asset_path("assets/delete_FILL0_wght700_GRAD0_opsz48.svg")
CANCEL_ICON_PATH = get_asset_path("assets/cancel_FILL0_wght700_GRAD0_opsz48.svg")


class MainWindowToolbar(ToolBar):
    new_transcription_action_triggered: pyqtSignal
    open_transcript_action_triggered: pyqtSignal
    clear_history_action_triggered: pyqtSignal
    ICON_LIGHT_THEME_BACKGROUND = "#555"
    ICON_DARK_THEME_BACKGROUND = "#AAA"

    def __init__(self, shortcuts: Dict[str, str], parent: Optional[QWidget]):
        super().__init__(parent)

        self.record_action = Action(Icon(RECORD_ICON_PATH, self), _("Record"), self)
        self.record_action.triggered.connect(self.on_record_action_triggered)

        self.new_transcription_action = Action(
            Icon(ADD_ICON_PATH, self), _("New Transcription"), self
        )
        self.new_transcription_action_triggered = (
            self.new_transcription_action.triggered
        )

        self.open_transcript_action = Action(
            Icon(EXPAND_ICON_PATH, self), _("Open Transcript"), self
        )
        self.open_transcript_action_triggered = self.open_transcript_action.triggered
        self.open_transcript_action.setDisabled(True)

        self.stop_transcription_action = Action(
            Icon(CANCEL_ICON_PATH, self), _("Cancel Transcription"), self
        )
        self.stop_transcription_action_triggered = (
            self.stop_transcription_action.triggered
        )
        self.stop_transcription_action.setDisabled(True)

        self.clear_history_action = Action(
            Icon(TRASH_ICON_PATH, self), _("Clear History"), self
        )
        self.clear_history_action_triggered = self.clear_history_action.triggered
        self.clear_history_action.setDisabled(True)

        self.set_shortcuts(shortcuts)

        self.addAction(self.record_action)
        self.addSeparator()
        self.addActions(
            [
                self.new_transcription_action,
                self.open_transcript_action,
                self.stop_transcription_action,
                self.clear_history_action,
            ]
        )
        self.setMovable(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

    def set_shortcuts(self, shortcuts: Dict[str, str]):
        self.record_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.OPEN_RECORD_WINDOW.name])
        )
        self.new_transcription_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.OPEN_IMPORT_WINDOW.name])
        )
        self.open_transcript_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.OPEN_TRANSCRIPT_EDITOR.name])
        )
        self.stop_transcription_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.STOP_TRANSCRIPTION.name])
        )
        self.clear_history_action.setShortcut(
            QKeySequence.fromString(shortcuts[Shortcut.CLEAR_HISTORY.name])
        )

    def on_record_action_triggered(self):
        recording_transcriber_window = RecordingTranscriberWidget(
            self, flags=Qt.WindowType.Window
        )
        recording_transcriber_window.show()

    def set_stop_transcription_action_enabled(self, enabled: bool):
        self.stop_transcription_action.setEnabled(enabled)

    def set_open_transcript_action_enabled(self, enabled: bool):
        self.open_transcript_action.setEnabled(enabled)

    def set_clear_history_action_enabled(self, enabled: bool):
        self.clear_history_action.setEnabled(enabled)


class MainWindow(QMainWindow):
    table_widget: TranscriptionTasksTableWidget
    tasks: Dict[int, "FileTranscriptionTask"]
    tasks_changed = pyqtSignal()
    openai_access_token: Optional[str]

    def __init__(self, tasks_cache=TasksCache()):
        super().__init__(flags=Qt.WindowType.Window)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(BUZZ_ICON_PATH))
        self.setMinimumSize(450, 400)

        self.setAcceptDrops(True)

        self.tasks_cache = tasks_cache

        self.settings = Settings()

        self.shortcut_settings = ShortcutSettings(settings=self.settings)
        self.shortcuts = self.shortcut_settings.load()
        self.default_export_file_name = self.settings.value(
            Settings.Key.DEFAULT_EXPORT_FILE_NAME,
            "{{ input_file_name }} ({{ task }}d on {{ date_time }})",
        )

        self.tasks = {}
        self.tasks_changed.connect(self.on_tasks_changed)

        self.toolbar = MainWindowToolbar(shortcuts=self.shortcuts, parent=self)
        self.toolbar.new_transcription_action_triggered.connect(
            self.on_new_transcription_action_triggered
        )
        self.toolbar.open_transcript_action_triggered.connect(
            self.open_transcript_viewer
        )
        self.toolbar.clear_history_action_triggered.connect(
            self.on_clear_history_action_triggered
        )
        self.toolbar.stop_transcription_action_triggered.connect(
            self.on_stop_transcription_action_triggered
        )
        self.addToolBar(self.toolbar)
        self.setUnifiedTitleAndToolBarOnMac(True)

        self.menu_bar = MenuBar(
            shortcuts=self.shortcuts,
            default_export_file_name=self.default_export_file_name,
            parent=self,
        )
        self.menu_bar.import_action_triggered.connect(
            self.on_new_transcription_action_triggered
        )
        self.menu_bar.shortcuts_changed.connect(self.on_shortcuts_changed)
        self.menu_bar.openai_api_key_changed.connect(
            self.on_openai_access_token_changed
        )
        self.menu_bar.default_export_file_name_changed.connect(
            self.default_export_file_name_changed
        )
        self.setMenuBar(self.menu_bar)

        self.table_widget = TranscriptionTasksTableWidget(self)
        self.table_widget.doubleClicked.connect(self.on_table_double_clicked)
        self.table_widget.return_clicked.connect(self.open_transcript_viewer)
        self.table_widget.itemSelectionChanged.connect(self.on_table_selection_changed)

        self.setCentralWidget(self.table_widget)

        # Start transcriber thread
        self.transcriber_thread = QThread()

        self.transcriber_worker = FileTranscriberQueueWorker()
        self.transcriber_worker.moveToThread(self.transcriber_thread)

        self.transcriber_worker.task_updated.connect(self.update_task_table_row)
        self.transcriber_worker.completed.connect(self.transcriber_thread.quit)

        self.transcriber_thread.started.connect(self.transcriber_worker.run)

        self.transcriber_thread.start()

        self.load_tasks_from_cache()

    def dragEnterEvent(self, event):
        # Accept file drag events
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        file_paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self.open_file_transcriber_widget(file_paths=file_paths)

    def on_file_transcriber_triggered(
        self, options: Tuple[TranscriptionOptions, FileTranscriptionOptions, str]
    ):
        transcription_options, file_transcription_options, model_path = options
        for file_path in file_transcription_options.file_paths:
            task = FileTranscriptionTask(
                file_path, transcription_options, file_transcription_options, model_path
            )
            self.add_task(task)

    def load_task(self, task: FileTranscriptionTask):
        self.table_widget.upsert_task(task)
        self.tasks[task.id] = task

    def update_task_table_row(self, task: FileTranscriptionTask):
        self.load_task(task=task)
        self.tasks_changed.emit()

    @staticmethod
    def task_completed_or_errored(task: FileTranscriptionTask):
        return (
            task.status == FileTranscriptionTask.Status.COMPLETED
            or task.status == FileTranscriptionTask.Status.FAILED
        )

    def on_clear_history_action_triggered(self):
        selected_rows = self.table_widget.selectionModel().selectedRows()
        if len(selected_rows) == 0:
            return

        reply = QMessageBox.question(
            self,
            _("Clear History"),
            _(
                "Are you sure you want to delete the selected transcription(s)? This action cannot be undone."
            ),
        )
        if reply == QMessageBox.StandardButton.Yes:
            task_ids = [
                TranscriptionTasksTableWidget.find_task_id(selected_row)
                for selected_row in selected_rows
            ]
            for task_id in task_ids:
                self.table_widget.clear_task(task_id)
                self.tasks.pop(task_id)
                self.tasks_changed.emit()

    def on_stop_transcription_action_triggered(self):
        selected_rows = self.table_widget.selectionModel().selectedRows()
        for selected_row in selected_rows:
            task_id = TranscriptionTasksTableWidget.find_task_id(selected_row)
            task = self.tasks[task_id]

            task.status = FileTranscriptionTask.Status.CANCELED
            self.tasks_changed.emit()
            self.transcriber_worker.cancel_task(task_id)
            self.table_widget.upsert_task(task)

    def on_new_transcription_action_triggered(self):
        (file_paths, __) = QFileDialog.getOpenFileNames(
            self, _("Select audio file"), "", SUPPORTED_OUTPUT_FORMATS
        )
        if len(file_paths) == 0:
            return

        self.open_file_transcriber_widget(file_paths)

    def open_file_transcriber_widget(self, file_paths: List[str]):
        file_transcriber_window = FileTranscriberWidget(
            file_paths=file_paths,
            default_output_file_name=self.default_export_file_name,
            parent=self,
            flags=Qt.WindowType.Window,
        )
        file_transcriber_window.triggered.connect(self.on_file_transcriber_triggered)
        file_transcriber_window.openai_access_token_changed.connect(
            self.on_openai_access_token_changed
        )
        file_transcriber_window.show()

    @staticmethod
    def on_openai_access_token_changed(access_token: str):
        KeyringStore().set_password(KeyringStore.Key.OPENAI_API_KEY, access_token)

    def default_export_file_name_changed(self, default_export_file_name: str):
        self.default_export_file_name = default_export_file_name
        self.settings.set_value(
            Settings.Key.DEFAULT_EXPORT_FILE_NAME, default_export_file_name
        )

    def open_transcript_viewer(self):
        selected_rows = self.table_widget.selectionModel().selectedRows()
        for selected_row in selected_rows:
            task_id = TranscriptionTasksTableWidget.find_task_id(selected_row)
            self.open_transcription_viewer(task_id)

    def on_table_selection_changed(self):
        self.toolbar.set_open_transcript_action_enabled(
            self.should_enable_open_transcript_action()
        )
        self.toolbar.set_stop_transcription_action_enabled(
            self.should_enable_stop_transcription_action()
        )
        self.toolbar.set_clear_history_action_enabled(
            self.should_enable_clear_history_action()
        )

    def should_enable_open_transcript_action(self):
        return self.selected_tasks_have_status([FileTranscriptionTask.Status.COMPLETED])

    def should_enable_stop_transcription_action(self):
        return self.selected_tasks_have_status(
            [
                FileTranscriptionTask.Status.IN_PROGRESS,
                FileTranscriptionTask.Status.QUEUED,
            ]
        )

    def should_enable_clear_history_action(self):
        return self.selected_tasks_have_status(
            [
                FileTranscriptionTask.Status.COMPLETED,
                FileTranscriptionTask.Status.FAILED,
                FileTranscriptionTask.Status.CANCELED,
            ]
        )

    def selected_tasks_have_status(self, statuses: List[FileTranscriptionTask.Status]):
        selected_rows = self.table_widget.selectionModel().selectedRows()
        if len(selected_rows) == 0:
            return False
        return all(
            [
                self.tasks[
                    TranscriptionTasksTableWidget.find_task_id(selected_row)
                ].status
                in statuses
                for selected_row in selected_rows
            ]
        )

    def on_table_double_clicked(self, index: QModelIndex):
        task_id = TranscriptionTasksTableWidget.find_task_id(index)
        self.open_transcription_viewer(task_id)

    def open_transcription_viewer(self, task_id: int):
        task = self.tasks[task_id]
        if task.status != FileTranscriptionTask.Status.COMPLETED:
            return

        transcription_viewer_widget = TranscriptionViewerWidget(
            transcription_task=task, parent=self, flags=Qt.WindowType.Window
        )
        transcription_viewer_widget.task_changed.connect(self.on_tasks_changed)
        transcription_viewer_widget.show()

    def add_task(self, task: FileTranscriptionTask):
        self.transcriber_worker.add_task(task)

    def load_tasks_from_cache(self):
        tasks = self.tasks_cache.load()
        for task in tasks:
            if (
                task.status == FileTranscriptionTask.Status.QUEUED
                or task.status == FileTranscriptionTask.Status.IN_PROGRESS
            ):
                task.status = None
                self.transcriber_worker.add_task(task)
            else:
                self.load_task(task=task)

    def save_tasks_to_cache(self):
        self.tasks_cache.save(list(self.tasks.values()))

    def on_tasks_changed(self):
        self.toolbar.set_open_transcript_action_enabled(
            self.should_enable_open_transcript_action()
        )
        self.toolbar.set_stop_transcription_action_enabled(
            self.should_enable_stop_transcription_action()
        )
        self.toolbar.set_clear_history_action_enabled(
            self.should_enable_clear_history_action()
        )
        self.save_tasks_to_cache()

    def on_shortcuts_changed(self, shortcuts: dict):
        self.shortcuts = shortcuts
        self.menu_bar.set_shortcuts(shortcuts=self.shortcuts)
        self.toolbar.set_shortcuts(shortcuts=self.shortcuts)
        self.shortcut_settings.save(shortcuts=self.shortcuts)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.transcriber_worker.stop()
        self.transcriber_thread.quit()
        self.transcriber_thread.wait()
        self.save_tasks_to_cache()
        self.shortcut_settings.save(shortcuts=self.shortcuts)
        super().closeEvent(event)


class Application(QApplication):
    window: MainWindow

    def __init__(self) -> None:
        super().__init__(sys.argv)

        self.setApplicationName(APP_NAME)
        self.setApplicationVersion(VERSION)

        self.window = MainWindow()
        self.window.show()

    def add_task(self, task: FileTranscriptionTask):
        self.window.add_task(task)
