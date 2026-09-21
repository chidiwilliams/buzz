import logging
import threading
import weakref
from contextlib import contextmanager

import sounddevice as sd


# PortAudio reads the list of audio devices once, when it initializes, and keeps
# using that snapshot. A device that appears or disappears later - Bluetooth
# headphones, a dock, or simply a change of the default output device in Windows
# - is invisible to us until PortAudio is re-initialized, which shows up as
# playback going to a device that is no longer there, i.e. silence.
#
# Re-initializing while a stream is open crashes PortAudio, so every stream we
# open is registered here and the refresh is skipped while any of them is alive.

# Weak, so a stream that is dropped without being closed cannot block refreshes forever.
_active_streams = weakref.WeakSet()
_lock = threading.RLock()


@contextmanager
def registered_stream(stream):
    """Mark a sounddevice stream as open, so devices are not refreshed under it."""
    with _lock:
        _active_streams.add(stream)
    try:
        yield stream
    finally:
        unregister_stream(stream)


def register_stream(stream) -> None:
    with _lock:
        _active_streams.add(stream)


def unregister_stream(stream) -> None:
    with _lock:
        _active_streams.discard(stream)


def refresh_audio_devices() -> bool:
    """Make PortAudio re-read the system's audio devices.

    Returns True when the device list was actually refreshed, False when it was
    skipped because a stream is still open or PortAudio refused to restart.
    """
    with _lock:
        if _active_streams:
            logging.debug("Skipping audio device refresh, %s stream(s) open", len(_active_streams))
            return False
        try:
            sd._terminate()
        except Exception:
            logging.warning("Could not shut down audio devices for a refresh", exc_info=True)
            return False

        try:
            sd._initialize()
        except Exception:
            # Leaving PortAudio down would break all playback, so try once more.
            logging.warning("Could not re-initialize audio devices, retrying", exc_info=True)
            try:
                sd._initialize()
            except Exception:
                logging.error("Audio devices are unavailable", exc_info=True)
            return False
    logging.debug("Refreshed audio devices")
    return True
