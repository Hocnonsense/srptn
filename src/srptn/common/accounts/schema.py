"""Canonical account schema.

There is no migration machinery: the schema is a single definition.  Opening
a database creates it when empty and otherwise verifies that it matches the
definition exactly, raising on any mismatch instead of trying to migrate.
"""

import sqlite3

SCHEMA = [
    """
    CREATE TABLE users (
        id            TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        role          TEXT NOT NULL
                      CHECK (role IN ('publisher', 'host', 'visitor')),
        is_active     INTEGER NOT NULL DEFAULT 1
                      CHECK (is_active IN (0, 1)),
        version       INTEGER NOT NULL DEFAULT 1,
        created_at    TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE account_events (
        event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        action      TEXT NOT NULL,
        operator_id TEXT,
        target_id   TEXT NOT NULL,
        created_at  TEXT NOT NULL
    )
    """,
    "CREATE INDEX account_events_target ON account_events (target_id)",
]

EXPECTED_COLUMNS = {
    "users": ["id", "password_hash", "role", "is_active", "version", "created_at"],
    "account_events": ["event_id", "action", "operator_id", "target_id", "created_at"],
}


def verify(conn: sqlite3.Connection):
    existing = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        )
    }
    if existing & EXPECTED_COLUMNS.keys():
        for table, expected in EXPECTED_COLUMNS.items():
            columns = [
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            if columns != expected:
                raise RuntimeError(
                    f"Account schema mismatch for table {table!r}: "
                    f"expected {expected}, found {columns}. "
                    "Delete the development database and retry.",
                )
    else:
        for statement in SCHEMA:
            conn.execute(statement)
