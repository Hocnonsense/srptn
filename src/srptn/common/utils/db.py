"""SQLite connection and transaction manager.

A generic wrapper: it opens connections and scopes transactions, but knows
nothing about the account schema.  Each operation opens a short-lived
connection; writes use ``BEGIN IMMEDIATE`` so concurrent registrations and
updates are serialized.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Database:
    """Owns a SQLite file and hands out connections and transactions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @contextmanager
    def connection(self):
        """Open an autocommit connection for reads."""
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """Open a write transaction, rolling back on any error."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
        except BaseException:
            conn.close()
            raise
        try:
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
