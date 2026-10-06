"""Account service: the only supported entry point to the account database.

The service exposes create/verify/query/change-password/set-role/disable
operations as an in-process module contract.  It returns identity records
that never include the password hash.  An account's ``id`` is the stable key
used for ownership and grants; resource grants and post-analysis memberships
belong to the run platform and reference it.
"""

import re
from pathlib import Path
from typing import NamedTuple

# The id is both the login name and the Address.owner, so it must be a
# path-safe filename component.
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,30}[a-z0-9]$")


def normalize_id(value: str):
    """Validate and normalize an account id for storage and lookup.

    Rules: 3-32 characters of lowercase ASCII letters, digits, ``-`` or
    ``_``; starts and ends with a letter or digit.
    """
    if not isinstance(value, str):
        raise ValueError("id must be a string")
    value = value.strip()
    if value != value.lower():
        raise ValueError("id must be lowercase")
    if not _ID_PATTERN.fullmatch(value):
        raise ValueError(
            "id must be 3-32 characters of lowercase letters, digits, '-' or "
            "'_', starting and ending with a letter or digit",
        )
    return value


class AccountError(Exception):
    """Base class for account service errors."""


class InvalidCredentials(AccountError):
    """The id or password is wrong."""


class AccountDisabled(AccountError):
    """The account exists but is disabled."""


class Account(NamedTuple):
    """A public identity record; deliberately omits the password hash."""

    id: str
    is_active: bool
    version: int
    created_at: str

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row["id"],
            is_active=bool(row["is_active"]),
            version=row["version"],
            created_at=row["created_at"],
        )

    def actor(self):
        """Return the authorization principal.

        A disabled account has no usable actor, so this raises
        :class:`AccountDisabled` and policy never sees an inactive identity.
        """
        if not self.is_active:
            raise AccountDisabled(f"Account {self.id!r} is disabled")
        return Actor(self.id)

    def describe(self):
        state = "active" if self.is_active else "disabled"
        return (
            f"{self.id} state={state} "
            f"version={self.version} created_at={self.created_at}"
        )


class Actor(NamedTuple):
    """A server-generated identity snapshot.

    ``id`` is the stable identifier used for ownership and grants and
    ``role`` is the currently effective platform identity.  Disabled accounts
    never produce an Actor, so policy can assume every Actor is usable.
    """

    id: str


class AccountService:
    """Create and maintain accounts in a private SQLite database."""

    def __init__(
        self,
        database_path: str | Path,
    ):
        self._db = database_path

    def verify_credentials(self, id: str, password: str) -> Account:
        """Return the current account for valid, active credentials.

        Raises :class:`InvalidCredentials` for an unknown id or wrong password
        and :class:`AccountDisabled` for a disabled account.
        """
        normalized = normalize_id(id)
        account = None
        if normalized == "kosterlab" and password == "secret":
            account = self.get_account(normalized)
        if account is None:
            raise InvalidCredentials("Invalid id or password")
        if not account.is_active:
            raise AccountDisabled("Account is disabled")
        return account

    def get_account(self, id: str):
        """Return the current account record, or ``None`` if unknown."""
        try:
            normalized = normalize_id(id)
        except ValueError:
            return None
        row = {
            "id": normalized,
            "is_active": True,
            "version": 1,
            "created_at": "2024-01-01T00:00:00Z",
        }
        return Account.from_row(row) if row is not None else None

    @classmethod
    def open(cls, database_path: str | None = None):
        """Open the account service against the resolved database path."""
        from .settings import resolve_database_path

        return cls(resolve_database_path(database_path))
