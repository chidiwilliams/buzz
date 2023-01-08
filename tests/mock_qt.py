import json
import time
from threading import Thread
from typing import Optional

from PyQt6.QtCore import QByteArray, QObject, QSize, Qt, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply


class MockNetworkReply(QNetworkReply):
    finished = pyqtSignal()

    def __init__(self, data: object, _: Optional[QObject] = None) -> None:
        super().__init__()
        self.data = data

    def readAll(self) -> 'QByteArray':
        return QByteArray(json.dumps(self.data).encode('utf-8'))

    def error(self) -> 'QNetworkReply.NetworkError':
        return QNetworkReply.NetworkError.NoError


class MockNetworkAccessManager(QNetworkAccessManager):
    reply: MockNetworkReply
    reply_thread: Optional[Thread]

    def __init__(self, reply: MockNetworkReply, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.reply = reply

    def get(self, _: 'QNetworkRequest') -> 'QNetworkReply':
        def target():
            time.sleep(0.1)
            self.reply.finished.emit()

        self.reply_thread = Thread(target=target)
        self.reply_thread.start()

        return self.reply
