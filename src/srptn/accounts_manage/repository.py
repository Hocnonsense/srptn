"""Management writes to accounts, used by the management CLI."""

import polars as pl

from ..common.accounts.policy import Role
from ..common.accounts.models import AccountStatus, Session, AccountEvent, EventLevel
from ..common.accounts.repository import AccountRepository


class ManageAccountRepository(AccountRepository):
    """Extend the account repository with status changes."""

    def set_status(
        self,
        session: Session,
        status: AccountStatus,
        *,
        operator_address: str,
    ):
        """Set the account status, bump ``version`` and log the change.

        ``session`` identifies the account (and the version it was read at);
        ``operator_address`` is the maintainer performing the change.
        """
        with self._database.transaction() as conn:
            self._check_version(conn, session)
            conn.execute(
                "UPDATE users SET status = ?, version = version + 1 WHERE id = ?",
                (status.value, session.id),
            )
            self._log(conn, f"set_status_{status.value}", operator_address, session.id)
        return self._account(session.id)

    def set_role(
        self,
        session: Session,
        role: Role,
        *,
        operator_address: str,
    ):
        """Set the account role, bump ``version`` and log the change."""
        with self._database.transaction() as conn:
            self._check_version(conn, session)
            conn.execute(
                "UPDATE users SET role = ?, version = version + 1 WHERE id = ?",
                (role.label, session.id),
            )
            self._log(conn, f"set_role_{role.label}", operator_address, session.id)
        return self._account(session.id)

    def list_accounts(self):
        """Return all accounts, optionally filtered by status."""
        with self._database.connection() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        return pl.DataFrame(
            {
                "id": [row["id"] for row in rows],
                "role": [Role.from_label(row["role"]).label for row in rows],
                "status": [AccountStatus(row["status"]) for row in rows],
            },
            schema={"id": pl.Utf8, "role": pl.Categorical, "status": pl.Categorical},
        )

    def events(self, target_id: str):
        """Return the audit events recorded for ``target_id``, oldest first."""
        with self._database.connection() as conn:
            rows = conn.execute(
                "SELECT level, action, operator_address, target_id, created_at "
                "FROM account_events WHERE target_id = ? ORDER BY event_id",
                (target_id,),
            ).fetchall()
        return [
            AccountEvent(
                level=EventLevel(row["level"]),
                action=row["action"],
                operator_address=row["operator_address"],
                target_id=row["target_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
