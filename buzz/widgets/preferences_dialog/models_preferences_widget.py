import logging
import os
import uuid
from typing import Optional

from PyQt6.QtCore import Qt, QThreadPool, QLocale, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QWidget,
    QFormLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QMessageBox,
    QHBoxLayout,
    QLayout,
    QToolButton,
    QFileDialog,
)

from buzz.locale import _
from buzz.model_loader import (
    ModelType,
    WhisperModelSize,
    TranscriptionModel,
    ModelDownloader,
    model_root_dir,
    get_whisper_cpp_custom_model_path,
)
from buzz.settings.settings import Settings
from buzz.settings.whisper_cpp_custom_models import (
    get_custom_models,
    add_custom_model,
)
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
        self.ui_locale = self.settings.value(Settings.Key.UI_LOCALE, QLocale().name())
        self.model_downloader: Optional[ModelDownloader] = None
        # Id of the custom model currently being downloaded from a URL, so the
        # downloaded file can be validated once the download completes.
        self.pending_custom_model_id: Optional[str] = None

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

        self._setup_model_type_section(layout, model_types)
        self._setup_model_list(layout)
        self._setup_custom_inputs(layout)
        self._setup_action_buttons(layout)

        self.reset()

        self.setLayout(layout)

    def _setup_model_type_section(self, layout, model_types):
        model_type_combo_box = ModelTypeComboBox(
            model_types=model_types,
            default_model=self.model.model_type if self.model is not None else None,
            parent=self,
        )
        model_type_combo_box.changed.connect(self.on_model_type_changed)

        info_button = QToolButton()
        info_button.setIcon(QIcon.fromTheme("dialog-information"))
        info_button.setToolTip(_("What model should I use?"))
        info_button.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://chidiwilliams.github.io/buzz/docs/faq#4-what-model-should-i-use")
        ))

        group_layout = QHBoxLayout()
        group_layout.addWidget(model_type_combo_box)
        group_layout.addWidget(info_button)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_widget = QWidget()
        group_widget.setLayout(group_layout)

        layout.addRow(_("Group"), group_widget)

    def _setup_model_list(self, layout):
        self.model_list_widget = QTreeWidget()
        self.model_list_widget.setColumnCount(1)
        self.model_list_widget.currentItemChanged.connect(self.on_model_size_changed)
        layout.addWidget(self.model_list_widget)

    def _setup_custom_inputs(self, layout):
        # Faster Whisper custom model: a Hugging Face model id.
        self.custom_model_id_input = HuggingFaceSearchLineEdit()
        self.custom_model_id_input.setObjectName("ModelIdInput")
        self.custom_model_id_input.setPlaceholderText(_("Huggingface ID of a Faster whisper model"))
        self.custom_model_id_input.textChanged.connect(self.on_custom_model_id_input_changed)
        layout.addRow("", self.custom_model_id_input)
        self.custom_model_id_input.hide()

        # Whisper.cpp custom models: name + (local file or download URL).
        self.custom_model_name_input = LineEdit()
        self.custom_model_name_input.setObjectName("ModelNameInput")
        self.custom_model_name_input.setPlaceholderText(_("Name for the custom model"))
        self.custom_model_name_input.textChanged.connect(
            self.on_custom_model_inputs_changed
        )
        layout.addRow("", self.custom_model_name_input)
        self.custom_model_name_input.hide()

        self.custom_model_link_input = LineEdit()
        self.custom_model_link_input.setMinimumWidth(255)
        self.custom_model_link_input.setObjectName("ModelLinkInput")
        self.custom_model_link_input.textChanged.connect(
            self.on_custom_model_inputs_changed
        )
        layout.addRow("", self.custom_model_link_input)
        self.custom_model_link_input.hide()

        custom_buttons_layout = QHBoxLayout()
        custom_buttons_layout.setContentsMargins(0, 0, 0, 0)

        self.browse_local_model_button = QPushButton(_("Add local model file"))
        self.browse_local_model_button.setObjectName("BrowseLocalModelButton")
        self.browse_local_model_button.clicked.connect(
            self.on_browse_local_model_button_clicked
        )
        custom_buttons_layout.addWidget(self.browse_local_model_button)

        self.add_custom_model_button = QPushButton(_("Add model from URL"))
        self.add_custom_model_button.setObjectName("AddCustomModelButton")
        self.add_custom_model_button.clicked.connect(
            self.on_add_custom_model_button_clicked
        )
        custom_buttons_layout.addWidget(self.add_custom_model_button)
        custom_buttons_layout.addStretch(1)

        self.custom_buttons_widget = QWidget()
        self.custom_buttons_widget.setLayout(custom_buttons_layout)
        layout.addRow("", self.custom_buttons_widget)
        self.custom_buttons_widget.hide()

    def _setup_action_buttons(self, layout):
        buttons_layout = QHBoxLayout()

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

    def on_model_size_changed(self, current: QTreeWidgetItem, _: QTreeWidgetItem):
        if current is None:
            return
        item_data = current.data(0, Qt.ItemDataRole.UserRole)
        if item_data is None:
            return
        # Item data is a (WhisperModelSize, custom_model_id) tuple.
        model_size, custom_model_id = item_data
        self.model.whisper_model_size = model_size
        self.model.custom_model_id = custom_model_id
        self.reset()

    def _is_whisper_cpp(self) -> bool:
        return self.model is not None and self.model.model_type == ModelType.WHISPER_CPP

    def reset(self):
        # reset buttons
        path = self.model.get_local_model_path()
        is_custom = self.model.whisper_model_size == WhisperModelSize.CUSTOM
        self.download_button.setVisible(path is None and not is_custom)
        self.download_button.setEnabled(not is_custom)
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

        # Faster Whisper custom model input (Hugging Face id)
        if (self.model.whisper_model_size == WhisperModelSize.CUSTOM
                and self.model.model_type == ModelType.FASTER_WHISPER):
            self.custom_model_id_input.show()
            self.download_button.setVisible(True)
            self.download_button.setEnabled(
                self.model.hugging_face_model_id != ""
            )
        else:
            self.custom_model_id_input.hide()

        # Whisper.cpp custom model inputs (name + local file / URL)
        if self._is_whisper_cpp():
            self.custom_model_link_input.setPlaceholderText(
                _("Download link to Whisper.cpp ggml model file")
            )
            self.custom_model_name_input.show()
            self.custom_model_link_input.show()
            self.custom_buttons_widget.show()
            self.on_custom_model_inputs_changed()
        else:
            self.custom_model_name_input.hide()
            self.custom_model_link_input.hide()
            self.custom_buttons_widget.hide()

        if self.model is None:
            return

        self._populate_model_list(downloaded_item, available_item)

    def _populate_model_list(self, downloaded_item, available_item):
        for model_size in WhisperModelSize:
            # Skip custom size for OpenAI Whisper
            if (self.model.model_type == ModelType.WHISPER and
                    model_size == WhisperModelSize.CUSTOM):
                continue

            # Whisper.cpp custom models are listed individually below, not as a
            # single generic "Custom" entry.
            if (model_size == WhisperModelSize.CUSTOM
                    and self.model.model_type == ModelType.WHISPER_CPP):
                continue

            # Skip LUMII size for all non Latvians
            if (model_size == WhisperModelSize.LUMII and
                    (self.model.model_type != ModelType.WHISPER_CPP or self.ui_locale != "lv_LV")):
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
            item.setData(0, Qt.ItemDataRole.UserRole, (model_size, None))
            if (self.model.whisper_model_size == model_size
                    and self.model.custom_model_id is None):
                item.setSelected(True)
            parent.addChild(item)

        # List each registered Whisper.cpp custom model by name.
        if self.model.model_type == ModelType.WHISPER_CPP:
            for custom_model in get_custom_models(model_root_dir):
                model = TranscriptionModel(
                    model_type=ModelType.WHISPER_CPP,
                    whisper_model_size=WhisperModelSize.CUSTOM,
                    custom_model_id=custom_model.id,
                )
                model_path = model.get_local_model_path()
                parent = downloaded_item if model_path is not None else available_item
                item = QTreeWidgetItem(parent)
                item.setText(0, custom_model.name or _("Custom"))
                item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    (WhisperModelSize.CUSTOM, custom_model.id),
                )
                if (self.model.whisper_model_size == WhisperModelSize.CUSTOM
                        and self.model.custom_model_id == custom_model.id):
                    item.setSelected(True)
                parent.addChild(item)

    def on_model_type_changed(self, model_type: ModelType):
        self.model.model_type = model_type
        self.model.custom_model_id = None
        self.reset()

    def on_custom_model_id_input_changed(self, text):
        self.model.hugging_face_model_id = text
        self.settings.save_custom_model_id(self.model)
        self.download_button.setEnabled(
            self.model.hugging_face_model_id != ""
        )

    def on_custom_model_inputs_changed(self, *_args):
        has_name = self.custom_model_name_input.text().strip() != ""
        has_url = self.custom_model_link_input.text().strip() != ""
        self.add_custom_model_button.setEnabled(has_name and has_url)
        self.browse_local_model_button.setEnabled(has_name)

    def on_browse_local_model_button_clicked(self):
        name = self.custom_model_name_input.text().strip()
        if not name:
            return

        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            _("Select Whisper.cpp model file"),
            "",
            _("Whisper.cpp model") + " (*.bin *.gguf);;" + _("All files") + " (*)",
        )
        if not file_path:
            return

        add_custom_model(name=name, path=file_path)
        self.custom_model_name_input.clear()
        self.custom_model_link_input.clear()
        self.reset()

    def on_add_custom_model_button_clicked(self):
        name = self.custom_model_name_input.text().strip()
        url = self.custom_model_link_input.text().strip()
        if not name or not url:
            return

        model_id = str(uuid.uuid4())
        destination = get_whisper_cpp_custom_model_path(model_id)
        add_custom_model(name=name, path=destination, source_url=url, model_id=model_id)

        self.pending_custom_model_id = model_id
        download_model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP,
            whisper_model_size=WhisperModelSize.CUSTOM,
            custom_model_id=model_id,
        )

        self.progress_dialog = ModelDownloadProgressDialog(
            model_type=ModelType.WHISPER_CPP,
            modality=self.progress_dialog_modality,
            parent=self,
        )
        self.progress_dialog.canceled.connect(self.on_progress_dialog_canceled)

        self.add_custom_model_button.setEnabled(False)
        self.model_downloader = ModelDownloader(
            model=download_model,
            custom_model_url=url,
        )
        self.model_downloader.signals.finished.connect(self.on_download_completed)
        self.model_downloader.signals.progress.connect(self.on_download_progress)
        self.model_downloader.signals.error.connect(self.on_download_error)
        QThreadPool().globalInstance().start(self.model_downloader)

    def on_download_button_clicked(self):
        self.progress_dialog = ModelDownloadProgressDialog(
            model_type=self.model.model_type,
            modality=self.progress_dialog_modality,
            parent=self,
        )
        self.progress_dialog.canceled.connect(self.on_progress_dialog_canceled)

        self.download_button.setEnabled(False)

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
            # If the deleted model was a custom one, fall back to a safe selection.
            if self.model.whisper_model_size == WhisperModelSize.CUSTOM:
                self.model.custom_model_id = None
            self.reset()

    def on_show_file_location_button_clicked(self):
        self.model.open_file_location()

    def on_download_completed(self, _: str):
        if self.pending_custom_model_id is not None:
            self.custom_model_name_input.clear()
            self.custom_model_link_input.clear()
            self.pending_custom_model_id = None

        self._close_progress_dialog()
        self.download_button.setEnabled(True)
        self.add_custom_model_button.setEnabled(True)
        self.reset()

    def on_download_error(self, error: str):
        if self.pending_custom_model_id is not None:
            # Remove the half-registered custom model on failure.
            from buzz.settings.whisper_cpp_custom_models import remove_custom_model

            remove_custom_model(self.pending_custom_model_id)
            self.pending_custom_model_id = None
        if self.progress_dialog is not None:
            self.progress_dialog.cancel()
        self._close_progress_dialog()
        self.download_button.setEnabled(True)
        self.add_custom_model_button.setEnabled(True)
        self.reset()
        download_failed_label = _('Download failed')
        QMessageBox.warning(self, _("Error"), f"{download_failed_label}: {error}")

    def on_download_progress(self, progress: tuple):
        if self.progress_dialog is not None and progress[1] != 0:
            self.progress_dialog.set_value(float(progress[0]) / progress[1])

    def on_progress_dialog_canceled(self):
        if self.model_downloader is not None:
            self.model_downloader.cancel()
        if self.pending_custom_model_id is not None:
            from buzz.settings.whisper_cpp_custom_models import remove_custom_model

            remove_custom_model(self.pending_custom_model_id)
            self.pending_custom_model_id = None
        self.add_custom_model_button.setEnabled(True)
        self.reset()

    def _close_progress_dialog(self):
        if self.progress_dialog is not None:
            self.progress_dialog.close()
            self.progress_dialog = None
