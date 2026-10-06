"""Account service: credential verification for the platform.

The base service composes an :class:`~.repository.AccountRepository` and
provides what the web login needs: verifying credentials and reading an
account.  Registration and password change live in the management package.
"""

import re

from .models import AccountDisabled, InvalidCredentials
from .passwords import BcryptPasswordHasher, PasswordHasher
from .repository import AccountRepository

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


class AccountService:
    """Account login operations."""

    @classmethod
    def open(
        cls,
        database_path: str | None = None,
        hasher: PasswordHasher | None = None,
    ):
        """Open the service against the resolved database path."""
        return cls(AccountRepository.load(database_path), hasher=hasher)

    def __init__(
        self,
        repository: AccountRepository,
        hasher: PasswordHasher | None = None,
    ):
        self._repository = repository
        self._hasher = hasher or BcryptPasswordHasher()

    def verify_credentials(self, id: str, password: str):
        """Return the current account for valid, active credentials.

        Raises :class:`InvalidCredentials` for an unknown id or wrong password
        and :class:`AccountDisabled` for a disabled account.
        """
        normalized = normalize_id(id)
        result = self._repository.get(normalized)
        if result is None:
            raise InvalidCredentials("Invalid id or password")
        account, password_hash = result
        if not self._hasher.verify(password, password_hash):
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
        result = self._repository.get(normalized)
        return result[0] if result is not None else None
