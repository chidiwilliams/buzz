import enum
import typing


class Shortcut(str, enum.Enum):
    sequence: str
    description: str

    def __new__(cls, sequence: str, description: str):
        obj = str.__new__(cls, sequence)
        obj._value_ = sequence
        obj.sequence = sequence
        obj.description = description
        return obj

    OPEN_RECORD_WINDOW = ("Ctrl+R", "Open Record Window")
    OPEN_IMPORT_WINDOW = ("Ctrl+O", "Import File")
    OPEN_IMPORT_URL_WINDOW = ("Ctrl+U", "Import URL")
    OPEN_PREFERENCES_WINDOW = ("Ctrl+,", "Open Preferences Window")

    VIEW_TRANSCRIPT_TEXT = ("Ctrl+E", "View Transcript Text")
    VIEW_TRANSCRIPT_TIMESTAMPS = ("Ctrl+T", "View Transcript Timestamps")

    CLEAR_HISTORY = ("Ctrl+S", "Clear History")
    STOP_TRANSCRIPTION = ("Ctrl+X", "Cancel Transcription")

    @staticmethod
    def get_default_shortcuts() -> typing.Dict[str, str]:
        return {shortcut.name: shortcut.sequence for shortcut in Shortcut}
