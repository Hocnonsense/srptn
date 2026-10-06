"""Time helpers shared by the account storage and service layers."""

from datetime import datetime, timezone


def utcnow():
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
