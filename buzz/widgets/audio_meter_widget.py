from typing import Optional

from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget


class AudioMeterWidget(QWidget):
    current_amplitude: float
    BAR_WIDTH = 2
    BAR_MARGIN = 1
    BAR_INACTIVE_COLOR: QColor
    BAR_ACTIVE_COLOR: QColor

    # Factor by which the amplitude is scaled to make the changes more visible
    DIFF_MULTIPLIER_FACTOR = 10
    SMOOTHING_FACTOR = 0.95

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumWidth(10)
        self.setFixedHeight(16)

        # Extra padding to fix layout
        self.PADDING_TOP = 3

        self.current_amplitude = 0.0

        self.MINIMUM_AMPLITUDE = 0.00005  # minimum amplitude to show the first bar
        self.AMPLITUDE_SCALE_FACTOR = 15  # scale the amplitudes such that 1/AMPLITUDE_SCALE_FACTOR will show all bars

        if self.palette().window().color().black() > 127:
            self.BAR_INACTIVE_COLOR = QColor("#555")
            self.BAR_ACTIVE_COLOR = QColor("#999")
        else:
            self.BAR_INACTIVE_COLOR = QColor("#BBB")
            self.BAR_ACTIVE_COLOR = QColor("#555")

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)

        rect = self.rect()
        center_x = rect.center().x()
        num_bars_in_half = int((rect.width() / 2) / (self.BAR_MARGIN + self.BAR_WIDTH))
        for i in range(num_bars_in_half):
            is_bar_active = (
                (self.current_amplitude - self.MINIMUM_AMPLITUDE)
                * self.AMPLITUDE_SCALE_FACTOR
            ) > (i / num_bars_in_half)
            painter.setBrush(
                self.BAR_ACTIVE_COLOR if is_bar_active else self.BAR_INACTIVE_COLOR
            )

            # draw to left
            painter.drawRect(
                center_x - ((i + 1) * (self.BAR_MARGIN + self.BAR_WIDTH)),
                rect.top() + self.PADDING_TOP,
                self.BAR_WIDTH,
                rect.height() - self.PADDING_TOP,
            )
            # draw to right
            painter.drawRect(
                center_x + (self.BAR_MARGIN + (i * (self.BAR_MARGIN + self.BAR_WIDTH))),
                rect.top() + self.PADDING_TOP,
                self.BAR_WIDTH,
                rect.height() - self.PADDING_TOP,
            )

    def update_amplitude(self, amplitude: float):
        self.current_amplitude = max(
            amplitude, self.current_amplitude * self.SMOOTHING_FACTOR
        )
        self.repaint()
