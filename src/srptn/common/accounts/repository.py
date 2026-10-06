"""Read and write access to accounts.

The repository owns the database connection and performs all reads and
writes, including timestamping, the ``version`` bump and audit logging.  It
never hashes or verifies passwords: it stores and returns the hash.
"""

import sqlite3

from ..utils.clock import utcnow
from ..utils.db import Database
from .models import Account, AccountStatus, EventLevel, Session
from .policy import Role


class AccountRepository:
    """Read/write access to the account table."""

    @classmethod
    def load(cls, database_path: str | None = None):
        """Open the database, creating the schema or verifying it matches."""
        from .schema import verify
        from .settings import resolve_database_path

        database = Database(resolve_database_path(database_path))
        with database.transaction() as conn:
            verify(conn)
        return cls(database)

    def __init__(self, database: Database):
        self._database = database

    def get(self, id: str) -> None | tuple[Account, str]:
        """Return ``(account, password_hash)`` or ``None`` if unknown."""
        with self._database.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (id,)).fetchone()
        if row is None:
            return None
        return (
            Account(
                id=row["id"],
                role=Role.from_label(row["role"]),
                status=AccountStatus(row["status"]),
                version=row["version"],
                created_at=row["created_at"],
            ),
            row["password_hash"],
        )

    def create(
        self,
        id: str,
        password_hash: str,
        role: Role,
        *,
        operator_address: str | None,
    ):
        """Insert a new on-hold account and record its registration event."""
        with self._database.transaction() as conn:
            if conn.execute("SELECT 1 FROM users WHERE id = ?", (id,)).fetchone():
                raise Account.Occupied(f"Account id {id!r} is taken")
            try:
                conn.execute(
                    "INSERT INTO users ("
                    "id, password_hash, role, status, version, created_at) "
                    "VALUES (?, ?, ?, 'onhold', 1, ?)",
                    (id, password_hash, role.label, utcnow()),
                )
            except sqlite3.IntegrityError as exc:
                raise Account.Occupied(f"Account id {id!r} is taken") from exc
            self._log(conn, "registered", operator_address, id)
        return self._account(id)

    def set_password_hash(
        self,
        session: Session,
        password_hash: str,
        *,
        operator_address: str | None = None,
    ):
        """Replace the password hash, bump ``version`` and log the change."""
        operator_address = operator_address or session.id
        with self._database.transaction() as conn:
            self._check_version(conn, session)
            conn.execute(
                "UPDATE users SET password_hash = ?, version = version + 1 "
                "WHERE id = ?",
                (password_hash, session.id),
            )
            self._log(conn, "password_changed", operator_address, session.id)
        return self._account(session.id)

    def log(
        self,
        action: str,
        operator_address: str | None,
        target_id: str,
        level: EventLevel = EventLevel.INFO,
    ):
        """Record an audit event (e.g. a login attempt).

        ``action`` is a free-form description of what happened; ``level``
        conveys its severity.
        """
        with self._database.transaction() as conn:
            self._log(conn, action, operator_address, target_id, level)

    def _check_version(
        self,
        conn: sqlite3.Connection,
        session: Session,
    ):
        row = conn.execute(
            "SELECT version FROM users WHERE id = ?",
            (session.id,),
        ).fetchone()
        if row is None:
            raise Account.NotFound(f"Unknown account id {session.id!r}")
        if row["version"] != session.version:
            raise Account.EditConflict("Account was modified; reload before saving")

    def _account(self, id: str):
        result = self.get(id)
        if result is None:  # pragma: no cover - the row was just written
            raise Account.NotFound(f"Unknown account id {id!r}")
        return result[0]

    @staticmethod
    def _log(
        conn: sqlite3.Connection,
        action: str,
        operator_address: str | None,
        target_id: str,
        level=EventLevel.INFO,
    ):
        conn.execute(
            "INSERT INTO account_events ("
            "level, action, operator_address, target_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (level.value, action, operator_address, target_id, utcnow()),
        )
