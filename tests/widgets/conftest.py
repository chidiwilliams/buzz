import logging
import pytest
from buzz.settings.settings import Settings


@pytest.fixture(scope="package")
def reset_settings():
    settings = Settings()
    settings.clear()
    settings.sync()
    logging.debug("Reset settings")
