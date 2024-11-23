from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QWidget

from buzz.assets import get_path


class Icon(QIcon):
    LIGHT_THEME_COLOR = "#555"
    DARK_THEME_COLOR = "#EEE"

    def __init__(self, path: str, parent: QWidget):
        super().__init__()
        self.path = path
        self.parent = parent

        self.color = self.get_color()
        normal_pixmap = self.create_default_pixmap(self.path, self.color)
        disabled_pixmap = self.create_disabled_pixmap(normal_pixmap, self.color)
        self.addPixmap(normal_pixmap, QIcon.Mode.Normal)
        self.addPixmap(disabled_pixmap, QIcon.Mode.Disabled)

    # https://stackoverflow.com/questions/15123544/change-the-color-of-an-svg-in-qt
    def create_default_pixmap(self, path, color):
        pixmap = QPixmap(path)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), color)
        painter.end()
        return pixmap

    def create_disabled_pixmap(self, pixmap, color):
        disabled_pixmap = QPixmap(pixmap.size())
        disabled_pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(disabled_pixmap)
        painter.setOpacity(0.4)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_DestinationIn
        )
        painter.fillRect(disabled_pixmap.rect(), color)
        painter.end()
        return disabled_pixmap

    def get_color(self) -> QColor:
        is_dark_theme = self.parent.palette().window().color().black() > 127
        return QColor(
            self.DARK_THEME_COLOR if is_dark_theme else self.LIGHT_THEME_COLOR
        )


class PlayIcon(Icon):
    def __init__(self, parent: QWidget):
        super().__init__(get_path("assets/play_arrow_black_24dp.svg"), parent)


class PauseIcon(Icon):
    def __init__(self, parent: QWidget):
        super().__init__(get_path("assets/pause_black_24dp.svg"), parent)


class UndoIcon(Icon):
    def __init__(self, parent: QWidget):
        super().__init__(get_path("assets/undo_FILL0_wght700_GRAD0_opsz48.svg"), parent)


class RedoIcon(Icon):
    def __init__(self, parent: QWidget):
        super().__init__(get_path("assets/redo_FILL0_wght700_GRAD0_opsz48.svg"), parent)


class FileDownloadIcon(Icon):
    def __init__(self, parent: QWidget):
        super().__init__(get_path("assets/file_download_black_24dp.svg"), parent)


class TranslateIcon(Icon):
    def __init__(self, parent: QWidget):
        super().__init__(get_path("assets/translate_black.svg"), parent)

class ResizeIcon(Icon):
    def __init__(self, parent: QWidget):
        super().__init__(get_path("assets/resize_black.svg"), parent)

class VisibilityIcon(Icon):
    def __init__(self, parent: QWidget):
        super().__init__(
            get_path("assets/visibility_FILL0_wght700_GRAD0_opsz48.svg"), parent
        )


BUZZ_ICON_PATH = get_path("assets/buzz.ico")
BUZZ_LARGE_ICON_PATH = get_path("assets/buzz-icon-1024.png")

INFO_ICON_PATH = get_path("assets/info-circle.svg")
RECORD_ICON_PATH = get_path("assets/mic_FILL0_wght700_GRAD0_opsz48.svg")
EXPAND_ICON_PATH = get_path("assets/open_in_full_FILL0_wght700_GRAD0_opsz48.svg")
ADD_ICON_PATH = get_path("assets/add_FILL0_wght700_GRAD0_opsz48.svg")
URL_ICON_PATH = get_path("assets/url.svg")
TRASH_ICON_PATH = get_path("assets/delete_FILL0_wght700_GRAD0_opsz48.svg")
CANCEL_ICON_PATH = get_path("assets/cancel_FILL0_wght700_GRAD0_opsz48.svg")
