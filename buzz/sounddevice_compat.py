"""Import sounddevice without letting a broken audio setup stop Buzz from starting.

sounddevice initializes PortAudio as soon as it is imported. That raises when
libportaudio is missing (OSError), and, since PortAudio 19.7 (Ubuntu 26.04 and
later), whenever its PulseAudio backend cannot reach a server (PortAudioError):
headless machines, CI runners, or a session without PipeWire or PulseAudio.

Import ``sounddevice`` and ``PortAudioError`` from here instead. When audio is
unavailable they are stand-ins: the device list is empty, and opening a stream
or querying a device raises ``PortAudioError``, which callers already handle
like any other audio device failure.
"""

import logging
from typing import Optional

AUDIO_UNAVAILABLE_REASON: Optional[str] = None

try:
    import sounddevice

    PortAudioError = sounddevice.PortAudioError
except Exception as exc:  # OSError, or PortAudioError from inside sounddevice
    AUDIO_UNAVAILABLE_REASON = str(exc) or type(exc).__name__
    logging.warning(
        "Audio devices are unavailable, recording and sounddevice playback are disabled: %s",
        AUDIO_UNAVAILABLE_REASON,
    )

    class PortAudioError(Exception):
        """Stand-in for sounddevice.PortAudioError when sounddevice cannot be imported."""

    class _UnavailableSoundDevice:
        """The subset of the sounddevice API Buzz uses, for when audio is unavailable."""

        PortAudioError = PortAudioError
        DeviceList = tuple

        class CallbackStop(Exception):
            pass

        class CallbackAbort(Exception):
            pass

        class _Default:
            device = (-1, -1)

        default = _Default()

        def __init__(self, reason: str):
            self._reason = reason

        def _error(self) -> PortAudioError:
            return PortAudioError(f"Audio devices are unavailable: {self._reason}")

        def query_devices(self, device=None, kind=None):
            if device is None and kind is None:
                return self.DeviceList()
            raise self._error()

        def query_hostapis(self, index=None):
            if index is None:
                return ()
            raise self._error()

        def check_input_settings(self, *args, **kwargs):
            raise self._error()

        def check_output_settings(self, *args, **kwargs):
            raise self._error()

        def InputStream(self, *args, **kwargs):
            raise self._error()

        def OutputStream(self, *args, **kwargs):
            raise self._error()

        def _initialize(self):
            pass

        def _terminate(self):
            pass

    sounddevice = _UnavailableSoundDevice(AUDIO_UNAVAILABLE_REASON)


def is_audio_available() -> bool:
    return AUDIO_UNAVAILABLE_REASON is None
