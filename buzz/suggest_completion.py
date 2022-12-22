import json
from typing import List

from PyQt6.QtCore import Qt, QPoint, QEvent, QTimer, QObject, QUrlQuery, QUrl, pyqtSignal, QMetaObject
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest, QNetworkAccessManager
from PyQt6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QAbstractItemView


class SuggestCompletion(QObject):
    error = pyqtSignal()
    selected = pyqtSignal(str)

    def __init__(self, parent: QLineEdit):
        super().__init__(parent)

        self.editor = parent

        # pop up
        self.popup = QListWidget()
        self.popup.setWindowFlags(Qt.WindowType.Popup)
        self.popup.setFocusProxy(self.editor)
        self.popup.setMouseTracking(True)
        self.popup.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.popup.installEventFilter(self)
        self.popup.itemClicked.connect(self.on_select_item)

    def eventFilter(self, target: QObject, event: QEvent):
        if target != self.popup:
            return False

        if event.type() == QEvent.Type.MouseButtonPress:
            self.popup.hide()
            self.editor.setFocus()
            return True

        if isinstance(event, QKeyEvent):
            key = event.key()
            if key in [Qt.Key.Key_Enter, Qt.Key.Key_Return]:
                self.on_select_item()
                return True

            if key == Qt.Key.Key_Escape:
                self.editor.setFocus()
                self.popup.hide()
                return True

            if key in [Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp,
                       Qt.Key.Key_PageDown]:
                return False

            self.editor.setFocus()
            self.editor.event(event)
            self.popup.hide()

        return False

    def on_select_item(self):
        self.popup.hide()
        self.editor.setFocus()

        item = self.popup.currentItem()
        self.editor.setText(item.text())
        QMetaObject.invokeMethod(self.editor, 'returnPressed')
        self.selected.emit(item.text())

    def on_request_response(self, network_reply: QNetworkReply):
        if network_reply.error() != QNetworkReply.NetworkError.NoError:
            self.error.emit()
            return

        response = json.loads(network_reply.readAll().data())

        self.popup.setUpdatesEnabled(False)
        self.popup.clear()

        for model in response:
            model_id = model.get('id')
            item = QListWidgetItem(self.popup)
            item.setText(model_id)

        self.popup.setCurrentItem(self.popup.item(0))
        self.popup.setFixedWidth(self.popup.sizeHintForColumn(0) + 20)
        self.popup.setUpdatesEnabled(True)
        self.popup.move(self.editor.mapToGlobal(QPoint(0, self.editor.height() + 5)))
        self.popup.setFocus()
        self.popup.show()
