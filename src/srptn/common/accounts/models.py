"""Account domain records, status, events and errors."""

from enum import Enum
from typing import NamedTuple

from .policy import Actor, Role


class AccountStatus(str, Enum):
    """Lifecycle state.  Non-active accounts may not log in."""

    ACTIVE = "active"
    ONHOLD = "onhold"


class Session(NamedTuple):
    """A logged-in session: the account id and the version it logged in with.

    Kept minimal and separate from :class:`Actor`: the version is session
    bookkeeping (revocation and optimistic concurrency), not authorization.
    """

    id: str
    version: int


class Account(NamedTuple):
    """A public identity record; deliberately omits the password hash."""

    id: str
    role: Role
    status: AccountStatus
    version: int
    created_at: str

    class Error(Exception):
        """Base class for account errors."""

    class Occupied(Error):
        """The id already exists."""

    class NotFound(Error):
        """No account exists for the given id."""

    class InvalidCredentials(Error):
        """The id or password is wrong."""

    class OnHold(Error):
        """The account exists but is not active (pending or suspended)."""

    class EditConflict(Error):
        """An update was rejected because the account changed since it was read."""

    @property
    def is_active(self):
        return self.status is AccountStatus.ACTIVE

    def actor(self):
        """Return the authorization principal (only for active accounts)."""
        if not self.is_active:
            raise Account.OnHold(f"Account {self.id!r} is on hold")
        return Actor(self.id, self.role)

    def session(self):
        return Session(self.id, self.version)

    def describe(self):
        return (
            f"{self.id}, {self.status.value} {self.role.label} "
            f"registered at {self.created_at}, {self.version} edits"
        )


class EventLevel(str, Enum):
    """Audit severity, named after UI alert levels.

    Only the severity is a fixed vocabulary; the ``action`` of an event is a
    free-form descriptive string so new situations do not require a schema or
    enum change.  ``danger`` reads as severity rather than as a Python error
    and maps directly onto alert styling.  Events never record secrets.
    """

    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"


class AccountEvent(NamedTuple):
    """A recorded audit event, as read back from the log."""

    level: EventLevel
    action: str
    operator_id: str | None
    target_id: str
    created_at: str
