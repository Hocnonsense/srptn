"""Account domain records and errors.

These carry identity and status, never the password hash.  An account's
``id`` is the stable key used for ownership and grants; resource grants and
post-analysis memberships belong to the run platform and reference it.
"""

from typing import NamedTuple

from .policy import Actor, Role


class AccountError(Exception):
    """Base class for account errors."""


class IdTaken(AccountError):
    """The id already exists."""


class AccountNotFound(AccountError):
    """No account exists for the given id."""


class InvalidCredentials(AccountError):
    """The id or password is wrong."""


class AccountDisabled(AccountError):
    """The account exists but is disabled."""


class StaleVersion(AccountError):
    """An update was rejected because the account changed since it was read."""


class Account(NamedTuple):
    """A public identity record; deliberately omits the password hash."""

    id: str
    role: Role
    is_active: bool
    version: int
    created_at: str

    def actor(self):
        """Return the authorization principal.

        A disabled account has no usable actor, so this raises
        :class:`AccountDisabled` and policy never sees an inactive identity.
        """
        if not self.is_active:
            raise AccountDisabled(f"Account {self.id!r} is disabled")
        return Actor(self.id, self.role)

    def describe(self):
        state = "active" if self.is_active else "disabled"
        return (
            f"{self.id}, {state} {self.role.value} "
            f"registered at {self.created_at}, {self.version} edits"
        )
