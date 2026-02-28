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

    def deleteLater(self) -> None:
        pass


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


class MockDownloadReply(QObject):
    """Mock reply for file downloads — supports downloadProgress and finished signals."""
    downloadProgress = pyqtSignal(int, int)
    finished = pyqtSignal()

    def __init__(
        self,
        data: bytes = b"fake-installer-data",
        network_error: "QNetworkReply.NetworkError" = QNetworkReply.NetworkError.NoError,
        error_string: str = "",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._network_error = network_error
        self._error_string = error_string
        self._aborted = False

    def readAll(self) -> QByteArray:
        return QByteArray(self._data)

    def error(self) -> "QNetworkReply.NetworkError":
        return self._network_error

    def errorString(self) -> str:
        return self._error_string

    def abort(self) -> None:
        self._aborted = True

    def deleteLater(self) -> None:
        pass

    def emit_finished(self) -> None:
        self.finished.emit()


class MockDownloadNetworkManager(QNetworkAccessManager):
    """Network manager that returns MockDownloadReply instances for each get() call."""

    def __init__(
        self,
        replies: Optional[list] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._replies = list(replies) if replies else []
        self._index = 0

    def get(self, _: "QNetworkRequest") -> "MockDownloadReply":
        if self._index < len(self._replies):
            reply = self._replies[self._index]
        else:
            reply = MockDownloadReply()
        self._index += 1
        return reply
