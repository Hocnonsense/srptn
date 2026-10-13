"""A validation issue tied to a dataset/row/column.

Kept in ``utils`` (not ``transform``) so both the table utilities and the
conversion layer can produce it without a circular import.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Issue:
    """A single validation problem, with the source it belongs to."""

    message: str
    dataset: str | None = None
    row: int | None = None
    column: str | None = None

    def __str__(self):
        location = " ".join(
            part
            for part in (
                f"dataset={self.dataset}" if self.dataset else "",
                f"row={self.row}" if self.row is not None else "",
                f"column={self.column}" if self.column else "",
            )
            if part
        )
        return f"{self.message} ({location})" if location else self.message
