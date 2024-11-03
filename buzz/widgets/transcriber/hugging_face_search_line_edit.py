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

        self.setMinimumWidth(255)

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
        self.clear()

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
        query.addQueryItem("filter", "whisper")
        query.addQueryItem("search", text)

        url.setQuery(query)

        return self.network_manager.get(QNetworkRequest(url))

    def on_popup_selected(self):
        self.timer.stop()

    def on_request_response(self, network_reply: QNetworkReply):
        if network_reply.error() != QNetworkReply.NetworkError.NoError:
            logging.debug(
                "Error fetching Hugging Face models: %s", network_reply.error()
            )
            return

        models = json.loads(network_reply.readAll().data())

        # TODO Possibly need to include text entered in the search box as item in popup
        #      as not all models are tagged with 'whisper'
        if len(models) > 0:
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
