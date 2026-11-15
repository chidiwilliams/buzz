import contextlib
import gc
import glob
import io
import multiprocessing
import os
import platform
import random
import shutil
import string
import sys
import tempfile
import weakref

# Disable the GUI startup update check during tests. The check fires an async
# QNetworkAccessManager HTTPS request which, while in flight, interferes with
# multiprocessing spawn on Windows and crashes child transcription processes.
# Tests must also never depend on network availability.
os.environ.setdefault("BUZZ_DISABLE_UPDATE_CHECK", "1")

import pytest

# Set multiprocessing to use 'spawn' instead of 'fork' on Linux
# This is required because Qt creates threads early, and forking a multi-threaded
# process can lead to deadlocks. The main application sets this in buzz/buzz.py.
if platform.system() != "Windows":
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass  # Already set
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QSettings, QThread
from PyQt6.QtSql import QSqlDatabase
from PyQt6.QtWidgets import QApplication
from _pytest.fixtures import SubRequest

# Keep tests away from the user's own Buzz settings: point every settings store
# at INI files in a temporary folder that is deleted after the run. Settings
# opens its store with QSettings.defaultFormat() so this applies on all
# platforms, the native format (registry, plists) cannot be moved.
# Child processes that import this file inherit the folder through the
# environment, so the run leaves no second folder behind.
if "BUZZ_TEST_SETTINGS_DIR" not in os.environ:
    os.environ["BUZZ_TEST_SETTINGS_DIR"] = tempfile.mkdtemp(
        prefix="buzz-test-settings-"
    )
TEST_SETTINGS_DIR = os.environ["BUZZ_TEST_SETTINGS_DIR"]
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(
    QSettings.Format.IniFormat, QSettings.Scope.UserScope, TEST_SETTINGS_DIR
)

from buzz.db.dao.transcription_dao import TranscriptionDAO
from buzz.db.dao.transcription_segment_dao import TranscriptionSegmentDAO
from buzz.db.db import setup_test_db
from buzz.db.service.transcription_service import TranscriptionService
from buzz.settings.settings import Settings
from buzz.settings.shortcuts import Shortcuts
from buzz.widgets.application import Application


def pytest_sessionstart(session):
    """Apply the submodule patches and rebuild the ctc_forced_aligner extension
    if it is out of date, like ``make test`` does. A plain ``pytest`` run would
    otherwise test against a stale build, which segfaults when it lacks a
    patched fix."""
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
    sys.path.insert(0, scripts_dir)
    try:
        import build_ctc_forced_aligner as aligner_build
    finally:
        sys.path.remove(scripts_dir)

    # Only its "already applied" notes go to stdout, warnings go to stderr
    with contextlib.redirect_stdout(io.StringIO()):
        aligner_build.apply_all_patches()
    if not aligner_build.is_up_to_date():
        aligner_build.build()


def pytest_unconfigure(config):
    shutil.rmtree(TEST_SETTINGS_DIR, ignore_errors=True)


def pytest_sessionfinish(session, exitstatus):
    """Destroy Qt objects left over by the tests while the QApplication is alive.

    At interpreter exit PyQt deletes every parentless QObject still owned by
    Python while walking sip's wrapper map. Deleting one of them can run Python
    code that creates or frees wrappers, which changes the map mid-walk and
    segfaults the run after all tests have passed. Deleting the leftovers here,
    from a snapshot, leaves nothing for that exit walk to do.
    """
    app = QApplication.instance()
    if app is None:
        return

    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()

    leftovers = []
    for obj in gc.get_objects():
        # A weak proxy passes isinstance checks for its referent, or raises
        # ReferenceError once that is gone; the referent is checked on its own
        if isinstance(obj, weakref.ProxyTypes):
            continue
        try:
            if (
                isinstance(obj, QObject)
                and obj is not app
                and not sip.isdeleted(obj)
                and sip.ispyowned(obj)
                and obj.parent() is None
            ):
                leftovers.append(obj)
        except RuntimeError:
            pass

    # Threads must be stopped before deletion, Qt aborts on deleting a running one
    for obj in leftovers:
        if isinstance(obj, QThread) and not sip.isdeleted(obj):
            obj.quit()
            obj.wait(5_000)

    main_thread = sip.unwrapinstance(QThread.currentThread())
    for obj in leftovers:
        if sip.isdeleted(obj):
            continue
        # Objects living in a still running worker thread can't be safely deleted from here
        thread = obj.thread()
        if thread is not None and sip.unwrapinstance(thread) != main_thread and thread.isRunning():
            continue
        if isinstance(obj, QThread) and obj.isRunning():
            continue
        sip.delete(obj)
    leftovers.clear()
    gc.collect()


@pytest.fixture()
def db(qapp) -> QSqlDatabase:
    # Qt's SQL module needs a QCoreApplication to be alive; opening a
    # QSqlDatabase without one segfaults, so depend on the app fixture even
    # though these tests never touch a widget.
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

    # Lives in TEST_SETTINGS_DIR, which is deleted after the run
    return Settings(application=application)


@pytest.fixture(scope="session")
def shortcuts(settings):
    return Shortcuts(settings)


@pytest.fixture(scope="session", autouse=True)
def cleanup_testdata_exports():
    """Remove transcription export files written into testdata/ during the test session.

    Transcription tests (e.g. the MainWindow flow) transcribe a bundled
    ``testdata/*.mp3`` with no explicit output directory, so the export lands
    next to the source as ``<name> (transcribed on <date>).<ext>``. Those export
    files are never checked in, so we additionally sweep that pattern at setup
    and teardown to clear artifacts leaked by a previous interrupted run.
    """
    testdata_dir = os.path.join(os.path.dirname(__file__), "..", "testdata")
    export_glob = os.path.join(testdata_dir, "* (transcribed on *)*")

    def _sweep_leaked_exports():
        for path in glob.glob(export_glob):
            try:
                os.remove(path)
            except OSError:
                pass

    _sweep_leaked_exports()
    before = set(glob.glob(os.path.join(testdata_dir, "*")))
    yield
    after = set(glob.glob(os.path.join(testdata_dir, "*")))
    for path in after - before:
        try:
            os.remove(path)
        except OSError:
            pass
    _sweep_leaked_exports()
