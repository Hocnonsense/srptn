"""Read access to accounts.

The base repository is read-only: it opens connections and returns stored
records.  The management package extends it with the write operations.
"""

from ..utils.db import Database
from .models import Account
from .policy import Role


class AccountRepository:
    """Read access to the account table."""

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
                role=Role(row["role"]),
                is_active=bool(row["is_active"]),
                version=row["version"],
                created_at=row["created_at"],
            ),
            row["password_hash"],
        )
