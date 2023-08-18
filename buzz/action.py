import typing

from PyQt6.QtGui import QAction, QKeySequence


class Action(QAction):
    def setShortcut(
        self,
        shortcut: typing.Union["QKeySequence", "QKeySequence.StandardKey", str, int],
    ) -> None:
        super().setShortcut(shortcut)
        self.setToolTip(Action.get_tooltip(self))

    @classmethod
    def get_tooltip(cls, action: QAction):
        tooltip = action.toolTip()
        shortcut = action.shortcut()

        if shortcut.isEmpty():
            return tooltip

        shortcut_text = shortcut.toString(QKeySequence.SequenceFormat.NativeText)
        return f"<p style='white-space:pre'>{tooltip}&nbsp;&nbsp;<code style='font-size:small'>{shortcut_text}</code></p>"
