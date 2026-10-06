"""Account roles and the authorization principal."""

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    """Platform identity.  Each account holds exactly one role."""

    PUBLISHER = "publisher"
    HOST = "host"
    VISITOR = "visitor"


@dataclass(frozen=True, slots=True)
class Actor:
    """A server-generated identity snapshot.

    ``id`` is the stable identifier used for ownership and grants and
    ``role`` is the currently effective platform identity.  Disabled accounts
    never produce an Actor, so policy can assume every Actor is usable.
    """

    id: str
    role: Role
