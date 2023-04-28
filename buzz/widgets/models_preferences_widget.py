from typing import Optional

from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtWidgets import QWidget, QFormLayout, QTreeWidget, QTreeWidgetItem, QPushButton, QMessageBox

from buzz.locale import _
from buzz.model_loader import ModelType, WhisperModelSize, get_local_model_path, TranscriptionModel, ModelDownloader
from buzz.widgets.model_download_progress_dialog import ModelDownloadProgressDialog
from buzz.widgets.model_type_combo_box import ModelTypeComboBox


class ModelsPreferencesWidget(QWidget):
    def __init__(self, progress_dialog_modality: Optional[Qt.WindowModality] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.model_downloader: Optional[ModelDownloader] = None
        self.model = TranscriptionModel(model_type=ModelType.WHISPER,
                                        whisper_model_size=WhisperModelSize.TINY)
        self.progress_dialog_modality = progress_dialog_modality

        self.progress_dialog: Optional[ModelDownloadProgressDialog] = None

        layout = QFormLayout()
        model_type_combo_box = ModelTypeComboBox(
            model_types=[ModelType.WHISPER, ModelType.WHISPER_CPP, ModelType.FASTER_WHISPER],
            default_model=self.model.model_type, parent=self)
        model_type_combo_box.changed.connect(self.on_model_type_changed)
        layout.addRow('Group', model_type_combo_box)

        self.model_list_widget = QTreeWidget()
        self.model_list_widget.setColumnCount(1)
        self.reset_model_size_list()
        self.model_list_widget.currentItemChanged.connect(self.on_model_size_changed)
        layout.addWidget(self.model_list_widget)

        self.download_button = QPushButton(_('Download'))
        self.download_button.clicked.connect(self.on_download_button_clicked)
        self.reset_download_button()
        layout.addWidget(self.download_button)

        self.setLayout(layout)

    def on_model_size_changed(self, current: QTreeWidgetItem, _: QTreeWidgetItem):
        if current is None:
            return
        item_data = current.data(0, Qt.ItemDataRole.UserRole)
        if item_data is None:
            return
        self.model.whisper_model_size = item_data
        self.reset_download_button()

    def reset_download_button(self):
        model_path = get_local_model_path(model=self.model)
        self.download_button.setEnabled(model_path is None)

    def on_model_type_changed(self, model_type: ModelType):
        self.model.model_type = model_type
        self.reset_model_size_list()
        self.reset_download_button()

    def on_download_button_clicked(self):
        self.progress_dialog = ModelDownloadProgressDialog(model_type=self.model.model_type,
                                                           modality=self.progress_dialog_modality, parent=self)
        self.progress_dialog.canceled.connect(self.on_progress_dialog_canceled)

        self.download_button.setEnabled(False)

        self.model_downloader = ModelDownloader(model=self.model)
        self.model_downloader.signals.finished.connect(self.on_download_completed)
        self.model_downloader.signals.progress.connect(self.on_download_progress)
        self.model_downloader.signals.error.connect(self.on_download_error)
        QThreadPool().globalInstance().start(self.model_downloader)

    def on_download_completed(self, _: str):
        self.progress_dialog = None

        self.reset_download_button()
        self.reset_model_size_list()

    def on_download_error(self, error: str):
        self.progress_dialog.cancel()
        self.progress_dialog = None

        self.reset_download_button()
        self.reset_model_size_list()
        QMessageBox.warning(self, _('Error'), f'Download failed: {error}')

    def on_download_progress(self, progress: tuple):
        self.progress_dialog.set_value(float(progress[0]) / progress[1])

    def reset_model_size_list(self):
        self.model_list_widget.clear()

        downloaded_item = QTreeWidgetItem(self.model_list_widget)
        downloaded_item.setText(0, _('Downloaded'))
        downloaded_item.setFlags(
            downloaded_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

        available_item = QTreeWidgetItem(self.model_list_widget)
        available_item.setText(0, _('Available for Download'))
        available_item.setFlags(
            available_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

        self.model_list_widget.addTopLevelItems([downloaded_item, available_item])
        self.model_list_widget.expandToDepth(2)
        self.model_list_widget.setHeaderHidden(True)
        self.model_list_widget.setAlternatingRowColors(True)

        for model_size in WhisperModelSize:
            model_path = get_local_model_path(
                model=TranscriptionModel(model_type=self.model.model_type, whisper_model_size=model_size))
            parent = downloaded_item if model_path is not None else available_item
            item = QTreeWidgetItem(parent)
            item.setText(0, model_size.value.title())
            item.setData(0, Qt.ItemDataRole.UserRole, model_size)
            if self.model.whisper_model_size == model_size:
                item.setSelected(True)
            parent.addChild(item)

    def on_progress_dialog_canceled(self):
        self.model_downloader.cancel()
        self.reset_model_size_list()
        self.reset_download_button()
