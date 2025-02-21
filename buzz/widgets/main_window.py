import os
import logging
import keyring
from typing import Tuple, List, Optional
from uuid import UUID

from PyQt6 import QtGui
from PyQt6.QtCore import (
    Qt,
    QThread,
    QModelIndex,
    pyqtSignal
)

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QFileDialog,
)

from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.file_transcriber_queue_worker import FileTranscriberQueueWorker
from buzz.locale import _
from buzz.settings.settings import APP_NAME, Settings
from buzz.settings.shortcuts import Shortcuts
from buzz.store.keyring_store import set_password, Key
from buzz.transcriber.transcriber import (
    FileTranscriptionTask,
    TranscriptionOptions,
    FileTranscriptionOptions,
    SUPPORTED_AUDIO_FORMATS,
    Segment,
)
from buzz.widgets.icon import BUZZ_ICON_PATH
from buzz.widgets.import_url_dialog import ImportURLDialog
from buzz.widgets.main_window_toolbar import MainWindowToolbar
from buzz.widgets.menu_bar import MenuBar
from buzz.widgets.snap_notice import SnapNotice
from buzz.widgets.preferences_dialog.models.preferences import Preferences
from buzz.widgets.transcriber.file_transcriber_widget import FileTranscriberWidget
from buzz.widgets.transcription_task_folder_watcher import (
    TranscriptionTaskFolderWatcher,
)
from buzz.widgets.transcription_tasks_table_widget import (
    TranscriptionTasksTableWidget,
)
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)


class MainWindow(QMainWindow):
    table_widget: TranscriptionTasksTableWidget
    transcriptions_updated = pyqtSignal(UUID)

    def __init__(self, transcription_service: TranscriptionService):
        super().__init__(flags=Qt.WindowType.Window)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(BUZZ_ICON_PATH))
        self.setBaseSize(1240, 600)
        self.resize(1240, 600)

        self.setAcceptDrops(True)

        self.settings = Settings()

        self.shortcuts = Shortcuts(settings=self.settings)

        self.quit_on_complete = False
        self.transcription_service = transcription_service

        self.toolbar = MainWindowToolbar(shortcuts=self.shortcuts, parent=self)
        self.toolbar.new_transcription_action_triggered.connect(
            self.on_new_transcription_action_triggered
        )
        self.toolbar.new_url_transcription_action_triggered.connect(
            self.on_new_url_transcription_action_triggered
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

        self.preferences = self.load_preferences(settings=self.settings)
        self.menu_bar = MenuBar(
            shortcuts=self.shortcuts,
            preferences=self.preferences,
            parent=self,
        )
        self.menu_bar.import_action_triggered.connect(
            self.on_new_transcription_action_triggered
        )
        self.menu_bar.import_url_action_triggered.connect(
            self.on_new_url_transcription_action_triggered
        )
        self.menu_bar.shortcuts_changed.connect(self.on_shortcuts_changed)
        self.menu_bar.openai_api_key_changed.connect(
            self.on_openai_access_token_changed
        )
        self.menu_bar.preferences_changed.connect(self.on_preferences_changed)
        self.setMenuBar(self.menu_bar)

        self.table_widget = TranscriptionTasksTableWidget(self)
        self.table_widget.doubleClicked.connect(self.on_table_double_clicked)
        self.table_widget.return_clicked.connect(self.open_transcript_viewer)
        self.table_widget.selectionModel().selectionChanged.connect(
            self.on_table_selection_changed
        )
        self.transcriptions_updated.connect(
            self.on_transcriptions_updated
        )

        self.setCentralWidget(self.table_widget)

        # Start transcriber thread
        self.transcriber_thread = QThread()

        self.transcriber_worker = FileTranscriberQueueWorker()
        self.transcriber_worker.moveToThread(self.transcriber_thread)

        self.transcriber_worker.task_started.connect(self.on_task_started)
        self.transcriber_worker.task_progress.connect(self.on_task_progress)
        self.transcriber_worker.task_download_progress.connect(
            self.on_task_download_progress
        )
        self.transcriber_worker.task_error.connect(self.on_task_error)
        self.transcriber_worker.task_completed.connect(self.on_task_completed)

        self.transcriber_worker.completed.connect(self.transcriber_thread.quit)

        self.transcriber_thread.started.connect(self.transcriber_worker.run)

        self.transcriber_thread.start()

        self.load_geometry()

        self.folder_watcher = TranscriptionTaskFolderWatcher(
            tasks={},
            preferences=self.preferences.folder_watch,
        )
        self.folder_watcher.task_found.connect(self.add_task)
        self.folder_watcher.find_tasks()

        self.transcription_viewer_widget = None

        # TODO Move this to the first user interaction with OpenAI api Key field
        #  that is the only place that needs access to password manager service
        if os.environ.get('SNAP_NAME', '') == 'buzz':
            logging.debug("Running in a snap environment")
            self.check_linux_permissions()

    def check_linux_permissions(self):
        try:
            _ = keyring.get_password(APP_NAME, username="random")
        except Exception:
            snap_notice = SnapNotice(self)
            snap_notice.show()

    def on_preferences_changed(self, preferences: Preferences):
        self.preferences = preferences
        self.save_preferences(preferences)
        self.folder_watcher.set_preferences(preferences.folder_watch)
        self.folder_watcher.find_tasks()

    def save_preferences(self, preferences: Preferences):
        self.settings.settings.beginGroup("preferences")
        preferences.save(self.settings.settings)
        self.settings.settings.endGroup()

    def load_preferences(self, settings: Settings):
        settings.settings.beginGroup("preferences")
        preferences = Preferences.load(settings.settings)
        settings.settings.endGroup()
        return preferences

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

        if file_transcription_options.file_paths is not None:
            for file_path in file_transcription_options.file_paths:
                task = FileTranscriptionTask(
                    transcription_options=transcription_options,
                    file_transcription_options=file_transcription_options,
                    model_path=model_path,
                    file_path=file_path,
                    source=FileTranscriptionTask.Source.FILE_IMPORT,
                )
                self.add_task(task)
        else:
            task = FileTranscriptionTask(
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                model_path=model_path,
                url=file_transcription_options.url,
                source=FileTranscriptionTask.Source.URL_IMPORT,
            )
            self.add_task(task)

    def on_clear_history_action_triggered(self):
        selected_rows = self.table_widget.selectionModel().selectedRows()
        if len(selected_rows) == 0:
            return

        question_box = QMessageBox()
        question_box.setWindowTitle(_("Clear History"))
        question_box.setIcon(QMessageBox.Icon.Question)
        question_box.setText(
            _(
                "Are you sure you want to delete the selected transcription(s)? "
                "This action cannot be undone."
            ),
        )
        question_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        question_box.button(QMessageBox.StandardButton.Yes).setText(_("Ok"))
        question_box.button(QMessageBox.StandardButton.No).setText(_("Cancel"))

        reply = question_box.exec()

        if reply == QMessageBox.StandardButton.Yes:
            self.table_widget.delete_transcriptions(selected_rows)

    def on_stop_transcription_action_triggered(self):
        selected_transcriptions = self.table_widget.selected_transcriptions()
        for transcription in selected_transcriptions:
            transcription_id = transcription.id_as_uuid
            self.transcriber_worker.cancel_task(transcription_id)
            self.transcription_service.update_transcription_as_canceled(
                transcription_id
            )
            self.table_widget.refresh_row(transcription_id)
            self.on_table_selection_changed()

    def on_new_transcription_action_triggered(self):
        (file_paths, __) = QFileDialog.getOpenFileNames(
            self, _("Select audio file"), "", SUPPORTED_AUDIO_FORMATS
        )
        if len(file_paths) == 0:
            return

        self.open_file_transcriber_widget(file_paths)

    def on_new_url_transcription_action_triggered(self):
        url = ImportURLDialog.prompt(parent=self)
        if url is not None:
            self.open_file_transcriber_widget(url=url)

    def open_file_transcriber_widget(
        self, file_paths: Optional[List[str]] = None, url: Optional[str] = None
    ):
        file_transcriber_window = FileTranscriberWidget(
            file_paths=file_paths,
            url=url,
            parent=self,
            flags=Qt.WindowType.Window,
        )
        file_transcriber_window.triggered.connect(self.on_file_transcriber_triggered)
        file_transcriber_window.openai_access_token_changed.connect(
            self.on_openai_access_token_changed
        )
        file_transcriber_window.show()
        file_transcriber_window.raise_()
        file_transcriber_window.activateWindow()

    @staticmethod
    def on_openai_access_token_changed(access_token: str):
        try:
            set_password(Key.OPENAI_API_KEY, access_token)
        except Exception as exc:
            logging.error("Unable to write to keyring: %s", exc)
            QMessageBox.critical(
                None, _("Error"), _("Unable to save OpenAI API key to keyring")
            )

    def open_transcript_viewer(self):
        selected_rows = self.table_widget.selectionModel().selectedRows()
        for selected_row in selected_rows:
            transcription = self.table_widget.transcription(selected_row)
            self.open_transcription_viewer(transcription)

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
        selected_transcriptions = self.table_widget.selected_transcriptions()
        if len(selected_transcriptions) == 0:
            return False
        return all(
            MainWindow.can_open_transcript(transcription)
            for transcription in selected_transcriptions
        )

    @staticmethod
    def can_open_transcript(transcription: Transcription) -> bool:
        return (
            FileTranscriptionTask.Status(transcription.status)
            == FileTranscriptionTask.Status.COMPLETED
        )

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
        transcriptions = self.table_widget.selected_transcriptions()
        if len(transcriptions) == 0:
            return False

        return all(
            [
                transcription.status_as_status in statuses
                for transcription in transcriptions
            ]
        )

    def on_table_double_clicked(self, index: QModelIndex):
        transcription = self.table_widget.transcription(index)
        if not MainWindow.can_open_transcript(transcription):
            return
        self.open_transcription_viewer(transcription)

    def open_transcription_viewer(self, transcription: Transcription):
        self.transcription_viewer_widget = TranscriptionViewerWidget(
            transcription=transcription,
            transcription_service=self.transcription_service,
            shortcuts=self.shortcuts,
            parent=self,
            flags=Qt.WindowType.Window,
            transcriptions_updated_signal=self.transcriptions_updated,
        )
        self.transcription_viewer_widget.show()

    def add_task(self, task: FileTranscriptionTask):
        self.transcription_service.create_transcription(task)
        self.table_widget.refresh_all()
        self.transcriber_worker.add_task(task)

    def on_transcriptions_updated(self):
        self.table_widget.refresh_all()

    def on_task_started(self, task: FileTranscriptionTask):
        self.transcription_service.update_transcription_as_started(task.uid)
        self.table_widget.refresh_row(task.uid)

    def on_task_progress(self, task: FileTranscriptionTask, progress: float):
        self.transcription_service.update_transcription_progress(task.uid, progress)
        self.table_widget.refresh_row(task.uid)

    def on_task_download_progress(
        self, task: FileTranscriptionTask, fraction_downloaded: float
    ):
        # TODO: Save download progress in the database
        pass

    def on_task_completed(self, task: FileTranscriptionTask, segments: List[Segment]):
        self.transcription_service.update_transcription_as_completed(task.uid, segments)
        self.table_widget.refresh_row(task.uid)

        if self.quit_on_complete:
            self.close()
            QApplication.quit()


    def on_task_error(self, task: FileTranscriptionTask, error: str):
        self.transcription_service.update_transcription_as_failed(task.uid, error)
        self.table_widget.refresh_row(task.uid)

        if self.quit_on_complete:
            self.close()
            QApplication.quit()

    def on_shortcuts_changed(self):
        self.menu_bar.reset_shortcuts()
        self.toolbar.reset_shortcuts()

    def resizeEvent(self, event):
        self.save_geometry()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.save_geometry()

        self.transcriber_worker.stop()
        self.transcriber_thread.quit()
        self.transcriber_thread.wait()

        if self.transcription_viewer_widget is not None:
            self.transcription_viewer_widget.close()

        super().closeEvent(event)

    def save_geometry(self):
        self.settings.begin_group(Settings.Key.MAIN_WINDOW)
        self.settings.settings.setValue("geometry", self.saveGeometry())
        self.settings.end_group()

    def load_geometry(self):
        self.settings.begin_group(Settings.Key.MAIN_WINDOW)
        geometry = self.settings.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.settings.end_group()
