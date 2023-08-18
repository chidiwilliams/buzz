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
    OPEN_PREFERENCES_WINDOW = ("Ctrl+,", "Open Preferences Window")

    OPEN_TRANSCRIPT_EDITOR = ("Ctrl+E", "Open Transcript Viewer")
    CLEAR_HISTORY = ("Ctrl+S", "Clear History")
    STOP_TRANSCRIPTION = ("Ctrl+X", "Cancel Transcription")

    @staticmethod
    def get_default_shortcuts() -> typing.Dict[str, str]:
        return {shortcut.name: shortcut.sequence for shortcut in Shortcut}
