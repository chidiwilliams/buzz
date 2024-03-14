# coding: utf-8
# https://gist.github.com/simonw/664b4b0851c1899dc55e1fb655181037

"""Simple declarative schema migration for SQLite.
See <https://david.rothlis.net/declarative-schema-migration-for-sqlite>.
Author: William Manley <will@stb-tester.com>.
Copyright Â© 2019-2022 Stb-tester.com Ltd.
License: MIT.
"""

import logging
import re
import sqlite3
from textwrap import dedent


def dumb_migrate_db(db, schema, allow_deletions=False):
    """
    Migrates a database to the new schema given by the SQL text `schema`
    preserving the data.  We create any table that exists in schema, delete any
    old table that is no longer used and add/remove columns and indices as
    necessary.
    Under this scheme there are a set of changes that we can make to the schema
    and this script will handle it fine:
    1. Adding a new table
    2. Adding, deleting or modifying an index
    3. Adding a column to an existing table as long as the new column can be
       NULL or has a DEFAULT value specified.
    4. Changing a column to remove NULL or DEFAULT as long as all values in the
       database are not NULL
    5. Changing the type of a column
    6. Changing the user_version
    In addition this function is capable of:
    1. Deleting tables
    2. Deleting columns from tables
    But only if allow_deletions=True.  If the new schema requires a column/table
    to be deleted and allow_deletions=False this function will raise
    `RuntimeError`.
    Note: When this function is called a transaction must not be held open on
    db.  A transaction will be used internally.  If you wish to perform
    additional migration steps as part of a migration use DBMigrator directly.
    Any internally generated rowid columns by SQLite may change values by this
    migration.
    """
    with DBMigrator(db, schema, allow_deletions) as migrator:
        migrator.migrate()
    return bool(migrator.n_changes)


class DBMigrator:
    def __init__(self, db, schema, allow_deletions=False):
        self.db = db
        self.schema = schema
        self.allow_deletions = allow_deletions

        self.pristine = sqlite3.connect(":memory:")
        self.pristine.executescript(schema)
        self.n_changes = 0

        self.orig_foreign_keys = None

    def log_execute(self, msg, sql, args=None):
        # It's important to log any changes we're making to the database for
        # forensics later
        msg_tmpl = "Database migration: %s with SQL:\n%s"
        msg_argv = (msg, _left_pad(dedent(sql)))
        if args:
            msg_tmpl += " args = %r"
            msg_argv += (args,)
        else:
            args = []
        logging.info(msg_tmpl, *msg_argv)
        self.db.execute(sql, args)
        self.n_changes += 1

    def __enter__(self):
        self.orig_foreign_keys = self.db.execute("PRAGMA foreign_keys").fetchone()[0]
        if self.orig_foreign_keys:
            self.log_execute(
                "Disable foreign keys temporarily for migration",
                "PRAGMA foreign_keys = OFF",
            )
            # This doesn't count as a change because we'll undo it at the end
            self.n_changes = 0

        self.db.__enter__()
        self.db.execute("BEGIN")
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.db.__exit__(exc_type, exc_value, exc_tb)
        if exc_value is None:
            # The SQLite docs say:
            #
            # > This pragma is a no-op within a transaction; foreign key
            # > constraint enforcement may only be enabled or disabled when
            # > there is no pending BEGIN or SAVEPOINT.
            old_changes = self.n_changes
            new_val = self._migrate_pragma("foreign_keys")
            if new_val == self.orig_foreign_keys:
                self.n_changes = old_changes

            # SQLite docs say:
            #
            # > A VACUUM will fail if there is an open transaction on the database
            # > connection that is attempting to run the VACUUM.
            if self.n_changes:
                self.db.execute("VACUUM")
        else:
            if self.orig_foreign_keys:
                self.log_execute(
                    "Re-enable foreign keys after migration", "PRAGMA foreign_keys = ON"
                )

    def migrate(self):
        # In CI the database schema may be changing all the time.  This checks
        # the current db and if it doesn't match database.sql we will
        # modify it so it does match where possible.
        pristine_tables = dict(
            self.pristine.execute(
                """\
            SELECT name, sql FROM sqlite_master
            WHERE type = \"table\" AND name != \"sqlite_sequence\""""
            ).fetchall()
        )
        pristine_indices = dict(
            self.pristine.execute(
                """\
            SELECT name, sql FROM sqlite_master
            WHERE type = \"index\""""
            ).fetchall()
        )

        tables = dict(
            self.db.execute(
                """\
            SELECT name, sql FROM sqlite_master
            WHERE type = \"table\" AND name != \"sqlite_sequence\""""
            ).fetchall()
        )

        new_tables = set(pristine_tables.keys()) - set(tables.keys())
        removed_tables = set(tables.keys()) - set(pristine_tables.keys())
        if removed_tables and not self.allow_deletions:
            raise RuntimeError(
                "Database migration: Refusing to delete tables %r" % removed_tables
            )

        modified_tables = set(
            name
            for name, sql in pristine_tables.items()
            if normalise_sql(tables.get(name, "")) != normalise_sql(sql)
        )

        # This PRAGMA is automatically disabled when the db is committed
        self.db.execute("PRAGMA defer_foreign_keys = TRUE")

        # New and removed tables are easy:
        for tbl_name in new_tables:
            self.log_execute("Create table %s" % tbl_name, pristine_tables[tbl_name])
        for tbl_name in removed_tables:
            self.log_execute("Drop table %s" % tbl_name, "DROP TABLE %s" % tbl_name)

        for tbl_name in modified_tables:
            # The SQLite documentation insists that we create the new table and
            # rename it over the old rather than moving the old out of the way
            # and then creating the new
            create_table_sql = pristine_tables[tbl_name]
            create_table_sql = re.sub(
                r"\b%s\b" % re.escape(tbl_name),
                tbl_name + "_migration_new",
                create_table_sql,
            )
            self.log_execute(
                "Columns change: Create table %s with updated schema" % tbl_name,
                create_table_sql,
            )

            cols = set(
                [x[1] for x in self.db.execute("PRAGMA table_info(%s)" % tbl_name)]
            )
            pristine_cols = set(
                [
                    x[1]
                    for x in self.pristine.execute("PRAGMA table_info(%s)" % tbl_name)
                ]
            )

            removed_columns = cols - pristine_cols
            if not self.allow_deletions and removed_columns:
                logging.warning(
                    "Database migration: Refusing to remove columns %r from "
                    "table %s.  Current cols are %r attempting migration to %r",
                    removed_columns,
                    tbl_name,
                    cols,
                    pristine_cols,
                )
                raise RuntimeError(
                    "Database migration: Refusing to remove columns %r from "
                    "table %s" % (removed_columns, tbl_name)
                )

            logging.info("cols: %s, pristine_cols: %s", cols, pristine_cols)
            self.log_execute(
                "Migrate data for table %s" % tbl_name,
                """\
                INSERT INTO {tbl_name}_migration_new ({common})
                SELECT {common} FROM {tbl_name}""".format(
                    tbl_name=tbl_name,
                    common=", ".join(cols.intersection(pristine_cols)),
                ),
            )

            # Don't need the old table any more
            self.log_execute(
                "Drop old table %s now data has been migrated" % tbl_name,
                "DROP TABLE %s" % tbl_name,
            )

            self.log_execute(
                "Columns change: Move new table %s over old" % tbl_name,
                "ALTER TABLE %s_migration_new RENAME TO %s" % (tbl_name, tbl_name),
            )

        # Migrate the indices
        indices = dict(
            self.db.execute(
                """\
            SELECT name, sql FROM sqlite_master
            WHERE type = \"index\""""
            ).fetchall()
        )
        for name in set(indices.keys()) - set(pristine_indices.keys()):
            self.log_execute(
                "Dropping obsolete index %s" % name, "DROP INDEX %s" % name
            )
        for name, sql in pristine_indices.items():
            if name not in indices:
                self.log_execute("Creating new index %s" % name, sql)
            elif sql != indices[name]:
                self.log_execute(
                    "Index %s changed: Dropping old version" % name,
                    "DROP INDEX %s" % name,
                )
                self.log_execute(
                    "Index %s changed: Creating updated version in its place" % name,
                    sql,
                )

        self._migrate_pragma("user_version")

        if self.pristine.execute("PRAGMA foreign_keys").fetchone()[0]:
            if self.db.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Database migration: Would fail foreign_key_check")

    def _migrate_pragma(self, pragma):
        pristine_val = self.pristine.execute("PRAGMA %s" % pragma).fetchone()[0]
        val = self.db.execute("PRAGMA %s" % pragma).fetchone()[0]

        if val != pristine_val:
            self.log_execute(
                "Set %s to %i from %i" % (pragma, pristine_val, val),
                "PRAGMA %s = %i" % (pragma, pristine_val),
            )

        return pristine_val


def _left_pad(text, indent="    "):
    """Maybe I can find a package in pypi for this?"""
    return "\n".join(indent + line for line in text.split("\n"))


def normalise_sql(sql):
    # Remove comments:
    sql = re.sub(r"--[^\n]*\n", "", sql)
    # Normalise whitespace:
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r" *([(),]) *", r"\1", sql)
    # Remove unnecessary quotes
    sql = re.sub(r'"(\w+)"', r"\1", sql)

    return sql.strip()
