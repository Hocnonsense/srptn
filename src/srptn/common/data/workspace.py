"""The per-address handle over the data store (filesystem only).

A ``Workspace`` binds one :class:`~.Address` and exposes its content, layout and
a lock.  ``with workspace as data_path`` flocks ``meta/{address}/.lock`` and
yields the data path.  It is not a security boundary: an executing shell gets a
real path, so isolation is a separate concern.
"""

from __future__ import annotations

import fcntl
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import polars as pl

    from . import Address, FileType
    from .fs import FSDataStore

LOCK_NAME = ".lock"


class Workspace:
    """Address-bound facade over a filesystem data store."""

    def __init__(self, store: "FSDataStore", address: "Address"):
        self.store = store
        self.address = address
        self._lock_file = None
        from . import FileType

        self.meta_path = self.store.files_path(self.address, FileType.META)
        self.data_path = self.store.files_path(self.address, FileType.DATA)

    # --- content (bound to the address) ---------------------------------

    def load_desc(self):
        return self.store.load_desc(self.address)

    def store_desc(self, desc: str):
        self.store.store_desc(self.address, desc)

    def load_sheet(self, name: str):
        return self.store.load_sheet(self.address, name)

    def store_sheet(self, sheet: pl.DataFrame, name: str):
        self.store.store_sheet(self.address, sheet, name)

    def has_sheet(self, name: str):
        return self.store.has_sheet(self.address, name)

    def load_file(self, path: str, file_type: FileType):
        return self.store.load_file(self.address, path, file_type)

    def store_file(self, file, path: str, file_type: FileType):
        self.store.store_file(self.address, file, path, file_type)

    def has_file(self, path: str, file_type: FileType):
        return self.store.has_file(self.address, path, file_type)

    def list_files(self, file_type: FileType):
        return self.store.list_files(self.address, file_type)

    # --- lifecycle ------------------------------------------------------

    def clean(self):
        self.store.clean(self.address)

    def __enter__(self):
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.meta_path.mkdir(parents=True, exist_ok=True)

        lock_path = self.meta_path / LOCK_NAME
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = lock_path.open("a")
        fcntl.flock(self._lock_file, fcntl.LOCK_EX)
        return self.data_path

    def __exit__(self, *exc):
        assert self._lock_file is not None
        fcntl.flock(self._lock_file, fcntl.LOCK_UN)
        self._lock_file.close()
        return False
