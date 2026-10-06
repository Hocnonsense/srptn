"""Account service: registration, login and password change.

The service composes a :class:`~.repository.AccountRepository` and adds
validation, password hashing and the account operations: registering an
on-hold account, verifying credentials and changing a password.
"""

import re

from .models import Account, EventLevel, Session
from .passwords import BcryptPasswordHasher, PasswordHasher, validate_password
from .policy import Role
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
    """Account registration, login and password change."""

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
        self._dummy_hash: str | None = None

    def verify_credentials(self, id: str, password: str):
        """Return the account for valid credentials of an active account.

        Unknown ids still run a dummy hash comparison so timing does not leak
        account existence.  Raises :class:`Account.InvalidCredentials` for an unknown
        id or wrong password and :class:`Account.OnHold` for a non-active one.
        """
        normalized = normalize_id(id)
        result = self._repository.get(normalized)
        if result is None:
            self._hasher.verify(password, self._dummy())
            self._repository.log("login_unknown_id", None, id, EventLevel.WARNING)
            raise Account.InvalidCredentials("Invalid id or password")
        account, password_hash = result
        if not self._hasher.verify(password, password_hash):
            self._repository.log(
                "login_wrong_password", account.id, account.id, EventLevel.WARNING
            )
            raise Account.InvalidCredentials("Invalid id or password")
        if not account.is_active:
            self._repository.log(
                "login_account_onhold", account.id, account.id, EventLevel.WARNING
            )
            raise Account.OnHold("Account is on hold, please contact an administrator")
        self._repository.log(
            "login_succeeded",
            account.id,
            account.id,
            EventLevel.SUCCESS,
        )
        return account

    def _dummy(self):
        """A lazily-computed hash used to equalize unknown-id timings."""
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash("dummy-password")
        return self._dummy_hash

    def get_account(self, id: str):
        """Return the current account record, or ``None`` if unknown."""
        try:
            normalized = normalize_id(id)
        except ValueError:
            return None
        result = self._repository.get(normalized)
        return result[0] if result is not None else None

    def change_password(
        self,
        session: Session,
        current_password: str,
        new_password: str,
    ):
        """Self-service password change for a logged-in session.

        The account is identified by the session (already authenticated), so
        the current password is only re-checked as a safeguard against an
        unattended session.  The session's version is used as the expected
        version, so it comes from server-side state and cannot be forged.
        """
        result = self._repository.get(session.id)
        if result is None:
            raise Account.NotFound(session.id)
        if not self._hasher.verify(current_password, result[1]):
            # A wrong current password is an input mistake, not an identity
            # failure: the session is already authenticated.
            self._repository.log(
                "password_change_wrong_current",
                session.id,
                session.id,
                EventLevel.WARNING,
            )
            raise ValueError("Current password is incorrect")
        validate_password(new_password)
        return self._repository.set_password_hash(
            session, self._hasher.hash(new_password)
        )

    def register(self, id: str, password: str):
        """Self-register an on-hold account.  A maintainer must approve it."""
        normalized = normalize_id(id)
        validate_password(password)
        return self._repository.create(
            normalized,
            self._hasher.hash(password),
            Role.VISITOR,
            operator_id=normalized,
        )
