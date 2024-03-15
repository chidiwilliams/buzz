import platform
import typing

from PyQt6 import QtGui
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QToolBar, QWidget


class ToolBar(QToolBar):
    def __init__(self, parent: typing.Optional[QWidget] = None):
        super().__init__(parent)

        self.setIconSize(QSize(18, 18))
        self.setStyleSheet("QToolButton{margin: 6px 3px;}")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

    def addAction(self, *args):
        action = super().addAction(*args)
        self.fix_spacing_on_mac()
        return action

    def addActions(self, actions: typing.Iterable[QtGui.QAction]) -> None:
        super().addActions(actions)
        self.fix_spacing_on_mac()

    def fix_spacing_on_mac(self):
        if platform.system() == "Darwin":
            self.widgetForAction(self.actions()[0]).setStyleSheet(
                "QToolButton { margin-left: 9px; margin-right: 1px; }"
            )
