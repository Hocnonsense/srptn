"""Account management service: approval, suspension and role changes."""

import polars as pl

from ..common.accounts.models import Account, AccountStatus
from ..common.accounts.passwords import PasswordHasher
from ..common.accounts.policy import Role
from ..common.accounts.service import AccountService

from .repository import ManageAccountRepository


class ManageAccountService(AccountService):
    """Compose the management repository and add approval/suspension."""

    _repository: ManageAccountRepository

    @classmethod
    def open(
        cls,
        database_path: str | None = None,
        hasher: PasswordHasher | None = None,
    ):
        repository = ManageAccountRepository.load(database_path)
        return cls(repository, hasher=hasher)

    def set_status(self, id: str, status: AccountStatus, *, operator_id: str):
        return self._repository.set_status(
            self._target_session(id), status, operator_id=operator_id
        )

    def set_role(self, id: str, role: Role, *, operator_id: str):
        return self._repository.set_role(
            self._target_session(id),
            role,
            operator_id=operator_id,
        )

    def account(self, id: str):
        """Return the account, raising :class:`Account.NotFound` if unknown."""
        account = self.get_account(id)
        if account is None:
            raise Account.NotFound(f"Unknown account id {id!r}")
        return account

    def history(self, id: str):
        """Return an account's audit events, oldest first."""
        return self._repository.events(self.account(id).id)

    def _target_session(self, id: str):
        """Load the account so the write is version-checked against it."""
        return self.account(id).session()

    def ls(self, status: str | None, role: str | None):
        status = AccountStatus(status) if status else None
        role = Role(role) if role else None
        accounts = self._repository.list_accounts()
        if status is not None:
            accounts = accounts.filter(pl.col("status") == status.value)
        if role is not None:
            accounts = accounts.filter(pl.col("role") == role.value)
        return accounts

    def stat(self, id: str):
        """Return a human-readable summary plus the account's audit events."""
        account = self.account(id)
        lines = [account.describe()]
        events = self.history(account.id)
        if not events:
            lines.append("  (no events)")
        for event in events:
            operator = event.operator_id or "-"
            lines.append(
                f"  {event.created_at}  {event.level.value:7} "
                f"{event.action}  (operator: {operator})"
            )
        return "\n".join(lines)
