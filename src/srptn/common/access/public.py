"""The central public index: which resources are published for everyone.

Built on the :class:`DataStore` abstraction: the list is stored as a
document, so this class does not depend on the storage backend (FS, S3, ...).
"""

import io
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import polars as pl

from ..data import Address

if TYPE_CHECKING:
    from ..data import DataStore

_SCHEMA = {
    "address": pl.Utf8,
    "entity_type": pl.Utf8,
    "owner": pl.Utf8,
    "published_at": pl.Utf8,
}

_DOCUMENT = "public/index.parquet"


class PublicIndex:
    """The list of resources published to everyone."""

    def __init__(self, store: DataStore, name: str = _DOCUMENT):
        self._store = store
        self._name = name

    def _read(self):
        data = self._store.load_global_meta(self._name)
        if data is None:
            return pl.DataFrame(schema=_SCHEMA)
        return pl.read_parquet(io.BytesIO(data))

    def _write(self, index: pl.DataFrame):
        buffer = io.BytesIO()
        index.write_parquet(buffer)
        self._store.store_global_meta(self._name, buffer.getvalue())

    def publish(self, address: Address):
        """Add ``address`` to the index (idempotent)."""
        index = self._read()
        if str(address) in set(index["address"]):
            return
        row = pl.DataFrame(
            {
                "address": [str(address)],
                "entity_type": [address.entity_type.__name__.lower()],
                "owner": [address.owner],
                "published_at": [datetime.now(timezone.utc).isoformat()],
            }
        )
        self._write(pl.concat([index, row], how="vertical"))

    def unpublish(self, address: Address):
        """Remove ``address`` from the index."""
        self._write(self._read().filter(pl.col("address") != str(address)))

    def contains(self, address: Address):
        """Whether ``address`` is published."""
        return str(address) in set(self._read()["address"])

    def addresses(self, entity_type=None):
        """Published addresses, optionally filtered by entity type."""
        index = self._read()
        if entity_type is not None:
            index = index.filter(pl.col("entity_type") == entity_type.__name__.lower())
        return [Address.from_str(value) for value in index["address"]]
