from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QWidget

from buzz.assets import get_asset_path


# TODO: move icons to Qt resources: https://stackoverflow.com/a/52341917/9830227
class Icon(QIcon):
    LIGHT_THEME_BACKGROUND = "#555"
    DARK_THEME_BACKGROUND = "#EEE"

    def __init__(self, path: str, parent: QWidget):
        # Adapted from https://stackoverflow.com/questions/15123544/change-the-color-of-an-svg-in-qt
        is_dark_theme = parent.palette().window().color().black() > 127
        color = self.get_color(is_dark_theme)

        pixmap = QPixmap(path)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
        painter.end()

        super().__init__(pixmap)

    def get_color(self, is_dark_theme):
        return (
            self.DARK_THEME_BACKGROUND if is_dark_theme else self.LIGHT_THEME_BACKGROUND
        )


class PlayIcon(Icon):
    def __init__(self, parent: QWidget):
        super().__init__(get_asset_path("assets/play_arrow_black_24dp.svg"), parent)


class PauseIcon(Icon):
    def __init__(self, parent: QWidget):
        super().__init__(get_asset_path("assets/pause_black_24dp.svg"), parent)


BUZZ_ICON_PATH = get_asset_path("assets/buzz.ico")
BUZZ_LARGE_ICON_PATH = get_asset_path("assets/buzz-icon-1024.png")
