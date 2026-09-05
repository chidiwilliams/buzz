import logging
import pytest
from unittest.mock import patch, MagicMock
from buzz.settings.settings import Settings


@pytest.fixture(autouse=True)
def mock_amplitude_listener_stream():
    # RecordingAmplitudeListener creates a real sounddevice.InputStream that
    # fires C-level callbacks from a background thread. If the Qt object is
    # deleted (via deleteLater + processEvents) while the C thread is still
    # active it causes a segfault or "Exception ignored from cffi callback"
    # that contaminates later tests.  Patch it out so no real audio hardware
    # stream is created during widget tests.
    mock_stream = MagicMock()
    mock_stream.samplerate = 16000
    with patch("buzz.recording.sounddevice.InputStream", return_value=mock_stream):
        yield


@pytest.fixture(autouse=True)
def mock_get_password():
    with patch("buzz.widgets.recording_transcriber_widget.get_password", return_value=None):
        yield


@pytest.fixture(autouse=True)
def mock_message_box():
    # Prevent QMessageBox dialogs from blocking tests (e.g. when a background
    # transcription thread emits an error after the test has already "passed")
    with patch("buzz.widgets.recording_transcriber_widget.QMessageBox"):
        yield


@pytest.fixture(autouse=True)
def force_gc_between_tests():
    yield
    from PyQt6.QtCore import QCoreApplication
    # Flush pending deleteLater() and queued cross-thread signals.
    # We intentionally do NOT call gc.collect() here: PyQt6 signal/slot
    # infrastructure can leave Python tuples with corrupted type pointers in
    # CPython's cyclic-GC tracking list, causing a PyTuple_GET_SIZE assertion
    # failure inside gc.collect(). Python's reference-counting handles
    # non-cyclic objects; PyQt6's own lifecycle management handles Qt cycles.
    for _ in range(3):
        QCoreApplication.processEvents()


@pytest.fixture(scope="package")
def reset_settings():
    settings = Settings()
    settings.clear()
    settings.sync()
    logging.debug("Reset settings")
