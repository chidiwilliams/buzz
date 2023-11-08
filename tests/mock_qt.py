import json
from typing import Optional

from PyQt6.QtCore import QByteArray, QObject, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class MockNetworkReply(QNetworkReply):
    def __init__(self, data: object, _: Optional[QObject] = None) -> None:
        self.data = data

    def readAll(self) -> "QByteArray":
        return QByteArray(json.dumps(self.data).encode("utf-8"))

    def error(self) -> "QNetworkReply.NetworkError":
        return QNetworkReply.NetworkError.NoError


class MockNetworkAccessManager(QNetworkAccessManager):
    finished = pyqtSignal(object)
    reply: MockNetworkReply

    def __init__(
        self, reply: MockNetworkReply, parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self.reply = reply

    def get(self, _: "QNetworkRequest") -> "QNetworkReply":
        self.finished.emit(self.reply)
        return self.reply
