import logging
from typing import Optional

from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtWidgets import (
    QWidget,
    QFormLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QMessageBox,
    QHBoxLayout,
    QLayout
)

from buzz.locale import _
from buzz.model_loader import (
    ModelType,
    WhisperModelSize,
    TranscriptionModel,
    ModelDownloader,
)
from buzz.settings.settings import Settings
from buzz.widgets.model_download_progress_dialog import ModelDownloadProgressDialog
from buzz.widgets.model_type_combo_box import ModelTypeComboBox
from buzz.widgets.line_edit import LineEdit
from buzz.widgets.transcriber.hugging_face_search_line_edit import (
    HuggingFaceSearchLineEdit,
)


class ModelsPreferencesWidget(QWidget):
    model: Optional[TranscriptionModel]

    def __init__(
        self,
        progress_dialog_modality=Qt.WindowModality.WindowModal,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.settings = Settings()
        self.model_downloader: Optional[ModelDownloader] = None

        model_types = [
            model_type
            for model_type in ModelType
            if model_type.is_available() and model_type.is_manually_downloadable()
        ]

        self.model = (
            TranscriptionModel(
                model_type=model_types[0], whisper_model_size=WhisperModelSize.TINY
            )
            if model_types[0] is not None
            else None
        )
        self.progress_dialog_modality = progress_dialog_modality

        self.progress_dialog: Optional[ModelDownloadProgressDialog] = None

        layout = QFormLayout()
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        model_type_combo_box = ModelTypeComboBox(
            model_types=model_types,
            default_model=self.model.model_type if self.model is not None else None,
            parent=self,
        )
        model_type_combo_box.changed.connect(self.on_model_type_changed)
        layout.addRow(_("Group"), model_type_combo_box)

        self.model_list_widget = QTreeWidget()
        self.model_list_widget.setColumnCount(1)
        self.model_list_widget.currentItemChanged.connect(self.on_model_size_changed)
        layout.addWidget(self.model_list_widget)

        buttons_layout = QHBoxLayout()

        self.custom_model_id_input = HuggingFaceSearchLineEdit()
        self.custom_model_id_input.setObjectName("ModelIdInput")

        self.custom_model_id_input.setPlaceholderText(_("Huggingface ID of a Faster whisper model"))
        self.custom_model_id_input.textChanged.connect(self.on_custom_model_id_input_changed)
        layout.addRow("", self.custom_model_id_input)
        self.custom_model_id_input.hide()

        self.custom_model_link_input = LineEdit()
        self.custom_model_link_input.setMinimumWidth(255)
        self.custom_model_link_input.setObjectName("ModelLinkInput")
        self.custom_model_link_input.textChanged.connect(self.on_custom_model_link_input_changed)
        layout.addRow("", self.custom_model_link_input)
        self.custom_model_link_input.hide()

        self.download_button = QPushButton(_("Download"))
        self.download_button.setObjectName("DownloadButton")
        self.download_button.clicked.connect(self.on_download_button_clicked)
        buttons_layout.addWidget(self.download_button)

        self.show_file_location_button = QPushButton(_("Show file location"))
        self.show_file_location_button.setObjectName("ShowFileLocationButton")
        self.show_file_location_button.clicked.connect(
            self.on_show_file_location_button_clicked
        )
        buttons_layout.addWidget(self.show_file_location_button)
        buttons_layout.addStretch(1)

        self.delete_button = QPushButton(_("Delete"))
        self.delete_button.setObjectName("DeleteButton")
        self.delete_button.clicked.connect(self.on_delete_button_clicked)
        buttons_layout.addWidget(self.delete_button)

        layout.addRow("", buttons_layout)

        self.reset()

        self.setLayout(layout)

    def on_model_size_changed(self, current: QTreeWidgetItem, _: QTreeWidgetItem):
        if current is None:
            return
        item_data = current.data(0, Qt.ItemDataRole.UserRole)
        if item_data is None:
            return
        self.model.whisper_model_size = item_data
        self.reset()

    def reset(self):
        # reset buttons
        path = self.model.get_local_model_path()
        self.download_button.setVisible(path is None)
        self.download_button.setEnabled(self.model.whisper_model_size != WhisperModelSize.CUSTOM)
        self.delete_button.setVisible(self.model.is_deletable())
        self.show_file_location_button.setVisible(self.model.is_deletable())

        # reset model list
        self.model_list_widget.clear()
        downloaded_item = QTreeWidgetItem(self.model_list_widget)
        downloaded_item.setText(0, _("Downloaded"))
        downloaded_item.setFlags(
            downloaded_item.flags() & ~Qt.ItemFlag.ItemIsSelectable
        )
        available_item = QTreeWidgetItem(self.model_list_widget)
        available_item.setText(0, _("Available for Download"))
        available_item.setFlags(available_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.model_list_widget.addTopLevelItems([downloaded_item, available_item])
        self.model_list_widget.expandToDepth(2)
        self.model_list_widget.setHeaderHidden(True)
        self.model_list_widget.setAlternatingRowColors(True)

        self.model.hugging_face_model_id = self.settings.load_custom_model_id(self.model)
        self.custom_model_id_input.setText(self.model.hugging_face_model_id)

        if (self.model.whisper_model_size == WhisperModelSize.CUSTOM
                and self.model.model_type == ModelType.FASTER_WHISPER):
            self.custom_model_id_input.show()
            self.download_button.setEnabled(
                self.model.hugging_face_model_id != ""
            )
        else:
            self.custom_model_id_input.hide()

        if self.model.model_type == ModelType.WHISPER_CPP:
            self.custom_model_link_input.setPlaceholderText(
                _("Download link to Whisper.cpp ggml model file")
            )

        if (self.model.whisper_model_size == WhisperModelSize.CUSTOM
                and self.model.model_type == ModelType.WHISPER_CPP
                and path is None):
            self.custom_model_link_input.show()
            self.download_button.setEnabled(
                self.custom_model_link_input.text() != "")
        else:
            self.custom_model_link_input.hide()

        if self.model is None:
            return

        for model_size in WhisperModelSize:
            # Skip custom size for OpenAI Whisper
            if (self.model.model_type == ModelType.WHISPER and
                    model_size == WhisperModelSize.CUSTOM):
                continue

            model = TranscriptionModel(
                model_type=self.model.model_type,
                whisper_model_size=WhisperModelSize(model_size),
                hugging_face_model_id=self.model.hugging_face_model_id,
            )
            model_path = model.get_local_model_path()
            parent = downloaded_item if model_path is not None else available_item
            item = QTreeWidgetItem(parent)
            item.setText(0, model_size.value.title())
            item.setData(0, Qt.ItemDataRole.UserRole, model_size)
            if self.model.whisper_model_size == model_size:
                item.setSelected(True)
            parent.addChild(item)

    def on_model_type_changed(self, model_type: ModelType):
        self.model.model_type = model_type
        self.reset()

    def on_custom_model_id_input_changed(self, text):
        self.model.hugging_face_model_id = text
        self.settings.save_custom_model_id(self.model)
        self.download_button.setEnabled(
            self.model.hugging_face_model_id != ""
        )

    def on_custom_model_link_input_changed(self, text):
        self.download_button.setEnabled(text != "")

    def on_download_button_clicked(self):
        self.progress_dialog = ModelDownloadProgressDialog(
            model_type=self.model.model_type,
            modality=self.progress_dialog_modality,
            parent=self,
        )
        self.progress_dialog.canceled.connect(self.on_progress_dialog_canceled)

        self.download_button.setEnabled(False)

        if (self.model.whisper_model_size == WhisperModelSize.CUSTOM and
                self.model.model_type == ModelType.WHISPER_CPP):
            self.model_downloader = ModelDownloader(
                model=self.model,
                custom_model_url=self.custom_model_link_input.text()
            )
        else:
            self.model_downloader = ModelDownloader(model=self.model)

        self.model_downloader.signals.finished.connect(self.on_download_completed)
        self.model_downloader.signals.progress.connect(self.on_download_progress)
        self.model_downloader.signals.error.connect(self.on_download_error)
        QThreadPool().globalInstance().start(self.model_downloader)

    def on_delete_button_clicked(self):
        reply = QMessageBox(self)
        reply.setWindowTitle(_("Delete Model"))
        reply.setText(_("Are you sure you want to delete the selected model?"))
        reply.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        ok_button = reply.button(QMessageBox.StandardButton.Yes)
        cancel_button = reply.button(QMessageBox.StandardButton.No)
        ok_button.setText(_("Ok"))
        cancel_button.setText(_("Cancel"))

        user_choice = reply.exec()

        if user_choice == QMessageBox.StandardButton.Yes:
            self.model.delete_local_file()
            self.reset()

    def on_show_file_location_button_clicked(self):
        self.model.open_file_location()

    def on_download_completed(self, _: str):
        self.progress_dialog = None
        self.download_button.setEnabled(True)
        self.reset()

    def on_download_error(self, error: str):
        self.progress_dialog.cancel()
        self.progress_dialog.close()
        self.progress_dialog = None
        self.download_button.setEnabled(True)
        self.reset()
        download_failed_label = _('Download failed')
        QMessageBox.warning(self, _("Error"), f"{download_failed_label}: {error}")

    def on_download_progress(self, progress: tuple):
        if progress[1] != 0:
            self.progress_dialog.set_value(float(progress[0]) / progress[1])

    def on_progress_dialog_canceled(self):
        self.model_downloader.cancel()
        self.reset()
