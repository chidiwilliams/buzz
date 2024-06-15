import enum
import typing
from buzz.locale import _


class Shortcut(str, enum.Enum):
    sequence: str
    description: str

    def __new__(cls, sequence: str, description: str):
        obj = str.__new__(cls, sequence)
        obj._value_ = sequence
        obj.sequence = sequence
        obj.description = description
        return obj

    OPEN_RECORD_WINDOW = ("Ctrl+R", _("Open Record Window"))
    OPEN_IMPORT_WINDOW = ("Ctrl+O", _("Import File"))
    OPEN_IMPORT_URL_WINDOW = ("Ctrl+U", _("Import URL"))
    OPEN_PREFERENCES_WINDOW = ("Ctrl+,", _("Open Preferences Window"))

    VIEW_TRANSCRIPT_TEXT = ("Ctrl+E", _("View Transcript Text"))
    VIEW_TRANSCRIPT_TRANSLATION = ("Ctrl+L", _("View Transcript Translation"))
    VIEW_TRANSCRIPT_TIMESTAMPS = ("Ctrl+T", _("View Transcript Timestamps"))

    CLEAR_HISTORY = ("Ctrl+S", _("Clear History"))
    STOP_TRANSCRIPTION = ("Ctrl+X", _("Cancel Transcription"))

    @staticmethod
    def get_default_shortcuts() -> typing.Dict[str, str]:
        return {shortcut.name: shortcut.sequence for shortcut in Shortcut}
