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
    SEARCH_TRANSCRIPT = ("Ctrl+F", _("Search Transcript"))
    SEARCH_NEXT = ("Ctrl+Return", _("Go to Next Transcript Search Result"))
    SEARCH_PREVIOUS = ("Shift+Return", _("Go to Previous Transcript Search Result"))
    SCROLL_TO_CURRENT_TEXT = ("Ctrl+G", _("Scroll to Current Text"))
    PLAY_PAUSE_AUDIO = ("Ctrl+P", _("Play/Pause Audio"))
    REPLAY_CURRENT_SEGMENT = ("Ctrl+Shift+P", _("Replay Current Segment"))
    TOGGLE_PLAYBACK_CONTROLS = ("Ctrl+Alt+P", _("Toggle Playback Controls"))

    DECREASE_SEGMENT_START = ("Ctrl+Left", _("Decrease Segment Start Time"))
    INCREASE_SEGMENT_START = ("Ctrl+Right", _("Increase Segment Start Time"))
    DECREASE_SEGMENT_END = ("Ctrl+Shift+Left", _("Decrease Segment End Time"))
    INCREASE_SEGMENT_END = ("Ctrl+Shift+Right", _("Increase Segment End Time"))

    CLEAR_HISTORY = ("Ctrl+S", _("Clear History"))
    STOP_TRANSCRIPTION = ("Ctrl+X", _("Cancel Transcription"))

    @staticmethod
    def get_default_shortcuts() -> typing.Dict[str, str]:
        return {shortcut.name: shortcut.sequence for shortcut in Shortcut}
