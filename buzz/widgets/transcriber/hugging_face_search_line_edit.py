import json
import logging
from typing import Optional

from PyQt6.QtCore import (
    pyqtSignal,
    QTimer,
    Qt,
    QMetaObject,
    QUrl,
    QUrlQuery,
    QPoint,
    QObject,
    QEvent,
)
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtWidgets import QListWidget, QWidget, QAbstractItemView, QListWidgetItem, QSizePolicy

from buzz.locale import _
from buzz.widgets.line_edit import LineEdit


def _has_native_asr_tags(tags: list[str]) -> bool:
    native_weights = "safetensors" in tags or "pytorch" in tags
    if "whisper" in tags:
        if "gguf" in tags and not native_weights:
            return False
        return "transformers" in tags or "peft" in tags
    if not native_weights:
        return False
    if ("mms" in tags and "wav2vec2" in tags) or any(
        tag in tags for tag in ("parakeet_ctc", "parakeet_rnnt", "parakeet_tdt")
    ):
        return True
    return "transformers" in tags and any(
        tag in tags for tag in ("qwen3_asr", "vibevoice_asr", "fun_asr_nano")
    )


# Adapted from https://github.com/ismailsunni/scripts/blob/master/autocomplete_from_url.py
class HuggingFaceSearchLineEdit(LineEdit):
    model_selected = pyqtSignal(str)
    popup: QListWidget

    def __init__(
        self,
        default_value: str = "",
        network_access_manager: Optional[QNetworkAccessManager] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(default_value, parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setPlaceholderText(_("Huggingface ID of a model"))

        self.setMinimumWidth(50)
        self.search_native_asr = False
        self._pending_reply: Optional[QNetworkReply] = None
        self._pending_search = None

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.fetch_models)

        # Restart debounce timer each time editor text changes
        self.textEdited.connect(self.timer.start)
        self.textEdited.connect(self.on_text_edited)

        if network_access_manager is None:
            network_access_manager = QNetworkAccessManager(self)

        self.network_manager = network_access_manager
        self.network_manager.finished.connect(self.on_request_response)

        self.popup = QListWidget()
        self.popup.setWindowFlags(Qt.WindowType.Popup)
        self.popup.setFocusProxy(self)
        self.popup.setMouseTracking(True)
        self.popup.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.popup.installEventFilter(self)
        self.popup.itemClicked.connect(self.on_select_item)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Defer selectAll to run after mouse events are processed
        QTimer.singleShot(0, self.selectAll)

    def on_text_edited(self, text: str):
        self.model_selected.emit(text)

    def on_select_item(self):
        self.popup.hide()
        self.setFocus()

        item = self.popup.currentItem()
        self.setText(item.text())
        QMetaObject.invokeMethod(self, "returnPressed")
        self.model_selected.emit(item.data(Qt.ItemDataRole.UserRole))

    def fetch_models(self):
        text = self.text()
        if len(text) < 3:
            return

        url = QUrl("https://huggingface.co/api/models")

        query = QUrlQuery()
        if self.search_native_asr:
            # Some native ASR models (e.g. VibeVoice) list ASR as a secondary Hub task.
            query.addQueryItem("filter", "automatic-speech-recognition")
            query.addQueryItem("sort", "downloads")
            query.addQueryItem("limit", "200")
            query.addQueryItem("expand", "tags")
        else:
            query.addQueryItem("filter", "whisper")
        query.addQueryItem("search", text)

        url.setQuery(query)

        self._pending_search = (text, self.search_native_asr)
        self._pending_reply = self.network_manager.get(QNetworkRequest(url))
        return self._pending_reply

    def on_request_response(self, network_reply: QNetworkReply):
        if self._pending_reply is not None and (
            network_reply != self._pending_reply
            or self._pending_search != (self.text(), self.search_native_asr)
        ):
            return
        if network_reply.error() != QNetworkReply.NetworkError.NoError:
            logging.debug(
                "Error fetching Hugging Face models: %s", network_reply.error()
            )
            return

        models = json.loads(network_reply.readAll().data())

        if self.search_native_asr:
            # The Hub also returns GGUF-only conversions and unrelated ASR
            # architectures. Keep suggestions within Buzz's native loaders.
            models = [model for model in models if _has_native_asr_tags(model.get("tags", []))]
        if not models:
            self.popup.clear()
            self.popup.hide()
            return

        self.popup.setUpdatesEnabled(False)
        self.popup.clear()

        for model in models:
            model_id = model.get("id")

            item = QListWidgetItem(self.popup)
            item.setText(model_id)
            item.setData(Qt.ItemDataRole.UserRole, model_id)

        self.popup.setCurrentItem(self.popup.item(0))
        self.popup.setFixedWidth(self.popup.sizeHintForColumn(0) + 20)
        self.popup.setFixedHeight(
            self.popup.sizeHintForRow(0) * min(len(models), 8)
        )  # show max 8 models, then scroll
        self.popup.setUpdatesEnabled(True)
        self.popup.move(self.mapToGlobal(QPoint(0, self.height())))
        self.popup.setFocus()
        self.popup.show()

    def eventFilter(self, target: QObject, event: QEvent):
        if hasattr(self, "popup") is False or target != self.popup:
            return False

        if event.type() == QEvent.Type.MouseButtonPress:
            self.popup.hide()
            self.setFocus()
            return True

        if isinstance(event, QKeyEvent):
            key = event.key()
            if key in [Qt.Key.Key_Enter, Qt.Key.Key_Return]:
                if self.popup.currentItem() is not None:
                    self.on_select_item()
                return True

            if key == Qt.Key.Key_Escape:
                self.setFocus()
                self.popup.hide()
                return True

            if key in [
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
                Qt.Key.Key_Home,
                Qt.Key.Key_End,
                Qt.Key.Key_PageUp,
                Qt.Key.Key_PageDown,
            ]:
                return False

            self.setFocus()
            self.event(event)
            self.popup.hide()

        return False
