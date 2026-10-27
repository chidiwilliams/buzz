from typing import Optional

from PyQt6 import QtGui
from PyQt6.QtCore import QRectF, QTimer, Qt
from PyQt6.QtGui import QPainter, QPalette, QPen
from PyQt6.QtWidgets import QPushButton, QWidget


class PlayButton(QPushButton):
    """
    A play button that can draw a circular progress around its icon, e.g.
    while the audio it plays is loading.
    """

    RING_WIDTH = 2
    # Busy spinner: the arc turns by SPIN_STEP degrees every SPIN_INTERVAL_MS
    SPIN_ARC = 90
    SPIN_STEP = 12
    SPIN_INTERVAL_MS = 33

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self._showing_progress = False
        # Percent done, or None while busy without a known amount of work
        self._progress: Optional[int] = None
        self._spin_angle = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(self.SPIN_INTERVAL_MS)
        self._spin_timer.timeout.connect(self._spin)

    @property
    def progress(self) -> Optional[int]:
        return self._progress

    @property
    def showing_progress(self) -> bool:
        return self._showing_progress

    def start_progress(self):
        """Shows a spinning arc until set_progress() or stop_progress() is called."""
        self._showing_progress = True
        self._progress = None
        self._spin_timer.start()
        self.update()

    def set_progress(self, percent: int):
        self._showing_progress = True
        self._progress = max(0, min(100, percent))
        self._spin_timer.stop()
        self.update()

    def stop_progress(self):
        self._showing_progress = False
        self._progress = None
        self._spin_timer.stop()
        self.update()

    def _spin(self):
        self._spin_angle = (self._spin_angle + self.SPIN_STEP) % 360
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        if not self._showing_progress:
            return

        # A ring just around the icon, kept inside the button
        icon_size = self.iconSize()
        diameter = min(max(icon_size.width(), icon_size.height()) + 8,
                       min(self.width(), self.height()) - 4)
        ring = QRectF(0, 0, diameter, diameter)
        ring.moveCenter(QRectF(self.rect()).center())
        inset = self.RING_WIDTH / 2
        ring.adjust(inset, inset, -inset, -inset)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.palette().color(QPalette.ColorRole.Mid), self.RING_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(ring)

        # The button is disabled while loading, which would grey this out too
        pen.setColor(self.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight))
        painter.setPen(pen)
        # Angles are in 1/16 degree, counterclockwise from 3 o'clock, so a
        # negative span from 90 degrees runs clockwise from 12 o'clock
        if self._progress is None:
            painter.drawArc(ring, (90 - self._spin_angle) * 16, -self.SPIN_ARC * 16)
        elif self._progress > 0:
            painter.drawArc(ring, 90 * 16, -round(self._progress * 360 / 100) * 16)
        painter.end()
