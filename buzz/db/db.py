import logging
import os
import sqlite3
import tempfile

from PyQt6.QtSql import QSqlDatabase
from platformdirs import user_data_dir

from buzz.db.helpers import (
    run_sqlite_migrations,
    copy_transcriptions_from_json_to_sqlite,
    mark_in_progress_and_queued_transcriptions_as_canceled,
)

APP_DB_PATH = os.path.join(user_data_dir("Buzz"), "Buzz.sqlite")


def setup_app_db() -> QSqlDatabase:
    return _setup_db(APP_DB_PATH)


def setup_test_db() -> QSqlDatabase:
    return _setup_db(tempfile.mktemp())


def _setup_db(path: str) -> QSqlDatabase:
    # Run migrations
    db = sqlite3.connect(path)
    run_sqlite_migrations(db)
    copy_transcriptions_from_json_to_sqlite(db)
    mark_in_progress_and_queued_transcriptions_as_canceled(db)
    db.close()

    db = QSqlDatabase.addDatabase("QSQLITE")
    db.setDatabaseName(path)
    if not db.open():
        raise RuntimeError(f"Failed to open database connection: {db.databaseName()}")
    logging.debug("Database connection opened: %s", db.databaseName())
    return db
