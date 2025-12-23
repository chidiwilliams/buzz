from PyQt6.QtGui import QIcon, QPixmap, QPainter, QPalette
from PyQt6.QtCore import QSize
from PyQt6.QtSvg import QSvgRenderer
import os
from buzz.assets import APP_BASE_DIR

class PresentationIcon:
    "Icons for presentation window controls"
    def __init__(self, parent, svg_path: str, color: str = None):
        self.parent = parent
        self.svg_path = svg_path
        self.color = color or self.get_default_color()


    def get_default_color(self) -> str:
        """Get default icon color based on theme"""
        palette = self.parent.palette()
        is_dark = palette.window().color().black() > 127

        return "#EEE" if is_dark else "#555"

    def get_icon(self) -> QIcon:
        """Load SVG icon and return as QIcon"""
        #Load from asset first
        full_path = os.path.join(APP_BASE_DIR, "assets", "icons", os.path.basename(self.svg_path))

        if not os.path.exists(full_path):
            pixmap = QPixmap(24, 24)
            pixmap.fill(self.color)

            return QIcon(pixmap)

        #Load SVG
        renderer = QSvgRenderer(full_path)
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        return QIcon(pixmap)



















