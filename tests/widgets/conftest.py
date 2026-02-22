import gc
import logging
import pytest
from unittest.mock import patch
from buzz.settings.settings import Settings


@pytest.fixture(autouse=True)
def mock_get_password():
    with patch("buzz.widgets.recording_transcriber_widget.get_password", return_value=None):
        yield


@pytest.fixture(autouse=True)
def force_gc_between_tests():
    yield
    gc.collect()


@pytest.fixture(scope="package")
def reset_settings():
    settings = Settings()
    settings.clear()
    settings.sync()
    logging.debug("Reset settings")
