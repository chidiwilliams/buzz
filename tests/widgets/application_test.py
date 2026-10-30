from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject

from buzz.widgets.application import CloseWindowShortcutFilter


def test_close_shortcut_filter_ignores_deleted_objects():
    """
    The filter sees the events of every object in the app, including ones
    being destroyed, which PyQt reports as deleted when passed back to Qt.
    """
    shortcut_filter = CloseWindowShortcutFilter()
    obj = QObject()
    sip.delete(obj)

    assert shortcut_filter.eventFilter(obj, QEvent(QEvent.Type.Show)) is False
