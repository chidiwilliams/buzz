from enum import Enum
from buzz.locale import _

class RecordingTranscriberMode(Enum):
    APPEND_BELOW = _("Append below")
    APPEND_ABOVE = _("Append above")
    APPEND_AND_CORRECT = _("Append and correct")