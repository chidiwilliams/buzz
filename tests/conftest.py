import os
import random
import string

import pytest
from PyQt6.QtSql import QSqlDatabase
from _pytest.fixtures import SubRequest

from buzz.db.dao.transcription_dao import TranscriptionDAO
from buzz.db.dao.transcription_segment_dao import TranscriptionSegmentDAO
from buzz.db.db import setup_test_db
from buzz.db.service.transcription_service import TranscriptionService
from buzz.settings.settings import Settings
from buzz.settings.shortcuts import Shortcuts
from buzz.widgets.application import Application


@pytest.fixture()
def db() -> QSqlDatabase:
    db = setup_test_db()
    yield db
    db.close()
    os.remove(db.databaseName())


@pytest.fixture()
def transcription_dao(db, request: SubRequest) -> TranscriptionDAO:
    dao = TranscriptionDAO(db)
    if hasattr(request, "param"):
        transcriptions = request.param
        for transcription in transcriptions:
            dao.insert(transcription)
    return dao


@pytest.fixture()
def transcription_service(
    transcription_dao, transcription_segment_dao
) -> TranscriptionService:
    return TranscriptionService(transcription_dao, transcription_segment_dao)


@pytest.fixture()
def transcription_segment_dao(db) -> TranscriptionSegmentDAO:
    return TranscriptionSegmentDAO(db)


@pytest.fixture(scope="session")
def qapp_cls():
    return Application


@pytest.fixture(scope="session")
def qapp_args(request):
    if not hasattr(request, "param"):
        return []

    return request.param


@pytest.fixture(scope="session")
def settings():
    application = "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(6)
    )

    settings = Settings(application=application)
    yield settings
    settings.clear()


@pytest.fixture(scope="session")
def shortcuts(settings):
    return Shortcuts(settings)
