"""Password hashing adapter.

Hashing uses the dedicated :mod:`bcrypt` library directly; the account layer
never implements a password algorithm itself.  The :class:`PasswordHasher`
protocol keeps the account service independent of the concrete hasher so it
can be swapped or faked in tests.
"""

from typing import Protocol

import bcrypt

# bcrypt silently truncates inputs beyond 72 bytes; reject them instead.
PASSWORD_MAX_BYTES = 72


class PasswordHasher(Protocol):
    """Hash and verify passwords without exposing stored hashes."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class BcryptPasswordHasher:
    """Default hasher using the ``bcrypt`` library."""

    def hash(self, password: str):
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(),
        ).decode("utf-8")

    def verify(self, password: str, password_hash: str):
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                password_hash.encode("utf-8"),
            )
        except (ValueError, TypeError):
            return False


def validate_password(password: str):
    """Reject empty or too-long passwords before hashing."""
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(
            f"Password must be at most {PASSWORD_MAX_BYTES} bytes",
        )
