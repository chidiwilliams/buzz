from typing import Optional, Tuple

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QValidator


class TemperatureValidator(QValidator):
    def __init__(self, parent: Optional[QObject] = ...) -> None:
        super().__init__(parent)

    def validate(
        self, text: str, cursor_position: int
    ) -> Tuple["QValidator.State", str, int]:
        try:
            temp_strings = [temp.strip() for temp in text.split(",")]
            if temp_strings[-1] == "":
                return QValidator.State.Intermediate, text, cursor_position
            _ = [float(temp) for temp in temp_strings]
            return QValidator.State.Acceptable, text, cursor_position
        except ValueError:
            return QValidator.State.Invalid, text, cursor_position
