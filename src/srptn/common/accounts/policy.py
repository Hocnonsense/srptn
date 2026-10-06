"""Account roles and the authorization principal.

Platform operations are qualified by role, ordered by capability:
``visitor < host < publisher``.  Resource-level authorization (ownership and
read/post-analysis grants) is resolved separately by the run platform against
actual resources, so it is not modelled here.
"""

from enum import IntEnum
from typing import NamedTuple


class Role(IntEnum):
    """Platform identity, ordered by capability.

    A role may perform every operation available to a lower role, so
    capability checks compare against a threshold (e.g. ``role >= Role.HOST``
    to create and run one's own analyses).
    """

    VISITOR = 0
    HOST = 1
    PUBLISHER = 2

    @property
    def label(self):
        """Lowercase name used for storage-independent display and input."""
        return self.name.lower()

    @classmethod
    def from_label(cls, label: str):
        """Parse a lowercase label such as ``"host"``."""
        return cls[label.strip().upper()]

    def permitted(self, min_role: "Role | None"):
        """Return whether this role is sufficient for a minimum role."""
        return min_role is None or self >= min_role


class Actor(NamedTuple):
    """A server-generated identity snapshot.

    ``id`` is the stable identifier used for ownership and grants and
    ``role`` is the currently effective platform identity.  Disabled accounts
    never produce an Actor, so callers can assume every Actor is usable.
    """

    id: str
    role: Role
