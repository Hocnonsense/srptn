"""Filesystem data store: content, a local workspace and the cache.

Cache is a filesystem-only capability here (git clones, scratch, versioned
entries, locks); remote backends raise for :meth:`workspace`.
"""

import fcntl
import shutil
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from . import E, Address, DataStore, Entity, FileType


@dataclass(slots=True)
class FSDataStore(DataStore):
    """A file-system data store."""

    base_data: Path = Path("datastore/data")
    base_meta: Path = Path("datastore/meta")
    base_cache: Path = Path("datastore/cache")
    base_global: Path = Path("datastore/global")

    # --- global metadata ------------------------------------------------

    def load_global_meta(self, name):
        path = self.base_global / name
        return path.read_bytes() if path.exists() else None

    def store_global_meta(self, name, data):
        path = self.base_global / name
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    # --- workspace / cache ----------------------------------------------

    def workspace(self, address: Address):
        from .workspace import Workspace

        return Workspace(self, address)

    def cache_entries(self, owner=None, filter=lambda x: x):
        if owner is not None:
            base = self.base_cache / f"private/.cache/{owner}"
            for marker in base.glob("**/.timestamp"):
                address = filter(marker.parent)
                if address is not None:
                    yield address, datetime.fromtimestamp(marker.stat().st_mtime)
        base = self.base_cache / "public/.cache"
        for marker in base.glob("**/.timestamp"):
            address = filter(marker.parent)
            if address is not None:
                yield address, datetime.fromtimestamp(marker.stat().st_mtime)

    @contextmanager
    def _cache_lock(self):
        self.base_cache.mkdir(parents=True, exist_ok=True)
        with (self.base_cache / ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def _cache(self, address, timestamp=None, replace=False):
        prefix = "private/" if isinstance(address, Address) else "public/"
        prefix += ".cache" if timestamp is None else f"{timestamp}"
        cache = self.as_path(self.base_cache, f"{prefix}/{address}")
        with self._cache_lock(), ExitStack() as locks:
            if replace:
                if cache.is_dir() and not cache.is_symlink():
                    # A replacement must also respect active nested entries.
                    for marker in sorted(cache.rglob(".timestamp")):
                        if marker.is_file() and not marker.is_symlink():
                            lock = locks.enter_context(marker.open("a"))
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if cache.is_symlink() or cache.is_file():
                    cache.unlink()
                elif cache.exists():
                    shutil.rmtree(cache)
            cache.mkdir(parents=True, exist_ok=True)
            marker = cache / ".timestamp"
            marker.touch()
            lock = marker.open("a")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if replace and isinstance(address, Address):
                    for file_type in (FileType.DATA, FileType.META):
                        source = self.files_path(address, file_type)
                        if source.exists() or source.is_symlink():
                            shutil.move(str(source), str(cache / file_type.value))
            except BaseException:
                lock.close()
                raise
        return cache, lock

    @contextmanager
    def cache_access(self, address, timestamp=None, replace=False):
        entry, lock = self._cache(address, timestamp, replace)
        with lock:
            try:
                yield entry
            finally:
                Path(lock.name).touch()

    def clean_cache(self, before):
        current = datetime.now(timezone.utc)
        if before.total_seconds() <= 0:
            raise ValueError("Cache expiry must be positive")
        cutoff = (current - before).timestamp()

        def prune(branch: Path, dated=False):
            if branch.is_symlink() or not branch.is_dir():
                # weird link exists without .timestamp, remove it
                branch.unlink()
                return False
            marker = branch / ".timestamp"
            if marker.is_file() and not marker.is_symlink():
                with marker.open("a") as lock:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        return True
                    if not dated and marker.stat().st_mtime >= cutoff:
                        return True
                    return prune_children(branch, dated)
            return prune_children(branch, dated)

        def prune_children(branch: Path, dated):
            retained = False
            for child in list(branch.iterdir()):
                if child.name != ".timestamp":
                    retained |= prune(child, dated)
            if not retained:
                shutil.rmtree(branch)
            return retained

        with self._cache_lock():
            for prefix in ("private", "public"):
                if not (self.base_cache / prefix).is_dir():
                    continue
                for entry in (self.base_cache / prefix).iterdir():
                    if entry.name == ".cache":
                        prune(entry)
                    elif entry.is_dir() and not entry.is_symlink():
                        try:
                            timestamp = datetime.fromisoformat(entry.name)
                        except ValueError:
                            continue
                        if timestamp.tzinfo is None:
                            timestamp = timestamp.replace(tzinfo=timezone.utc)
                        if current - timestamp > before:
                            prune(entry, dated=True)

    def clean(self, address):
        """Move metadata and data into cache for external garbage collection."""
        with self.cache_access(address, datetime.now(timezone.utc), replace=True):
            pass

    def load_sheet(self, address, sheet_name):
        """Load a sample sheet as a Polars DataFrame from the given address."""
        return pl.read_parquet(self.sheet_path(address, sheet_name))

    def has_sheet(self, address, sheet_name):
        """Check if a sample sheet exists for the given address and sheet name."""
        return self.sheet_path(address, sheet_name).exists()

    def load_desc(self, address):
        """Load and returns the description text for the given address."""
        return self.desc_path(address).read_text()

    def load_file(self, address, file_path, file_type):
        """Load a file of a specific type from the given address."""
        return (self.files_path(address, file_type) / file_path).open("rb")

    def has_file(self, address, file_path, file_type):
        """Check if a file exists for the given address, path, and file type."""
        return (self.files_path(address, file_type) / file_path).exists()

    def list_files(self, address: Address, file_type: FileType):
        """List all files of a specific type at the given address."""
        files_dir = self.files_path(address, file_type)
        if files_dir.exists():
            return pl.DataFrame(
                [
                    (f.name, f.stat().st_size)
                    for f in files_dir.iterdir()
                    if f.is_file()
                ],
                schema=["name", "size"],
                orient="row",
            )
        return pl.DataFrame(schema=["name", "size"])

    def store_file(self, address, file, file_path, file_type):
        """Store a file of a specific type at the given address."""
        folder = self.files_path(address, file_type)
        file_path_ = folder / file_path
        file_path_.parent.mkdir(exist_ok=True, parents=True)
        with (file_path_).open("wb") as f:
            shutil.copyfileobj(file, f)

    def store_desc(self, address, desc):
        """Store the description text for the given address."""
        desc_path = self.desc_path(address)
        desc_path.parent.mkdir(exist_ok=True, parents=True)
        desc_path.write_text(desc)

    def store_sheet(self, address, sheet, sheet_name):
        """Store a sample sheet as a Parquet file at the given address."""
        sheet_path = self.sheet_path(address, sheet_name)
        sheet_path.parent.mkdir(exist_ok=True, parents=True)
        try:
            sheet.write_parquet(sheet_path)
        except Exception as e:
            raise RuntimeError(f"Failed to write sheet to {sheet_path}: {e}") from e

    def entities(self, entity_type: type[E], search_term=None, *, owned_by=None):
        """Retrieve entities of a specific type, filtered by search term and owner."""
        addr_ = (
            Address.from_str(str(desc.parent.relative_to(self.base_meta)))
            for desc in self.base_meta.glob("**/desc.md")
        )
        addr = (a for a in addr_ if a.entity_type == entity_type)

        search_filter_func = owned_filter_func = lambda entity: True

        if search_term:  # match the keyword

            def search_filter_func(entity: Entity):
                return search_term in str(entity.address) or search_term in entity.desc

        if owned_by:  # safety

            def owned_filter_func(entity: Entity):
                return entity.address.owner == owned_by

        return list(
            filter(
                search_filter_func,
                filter(owned_filter_func, (entity_type.load(self, a) for a in addr)),
            ),
        )

    def occupied(self, address, only_check_meta=False):
        """Check if an entity exists for the given address,
        or if it is inside any of the data store's file types.
        """
        if not only_check_meta:
            if self.desc_path(address).exists():
                return True
        if self.files_path(address, FileType.DATA).exists():
            return True
        for parent in self.files_path(address, FileType.META).parents:
            if (parent / "desc.md").exists():
                return True
            if parent == self.base_meta:
                break
        return False

    @staticmethod
    def as_path(base: Path, address):
        """Convert a base path and address into a full path."""
        return base / str(address)

    def desc_path(self, address: Address):
        """Return the path to the description file for the given address."""
        return self.files_path(address, FileType.META) / "desc.md"

    def sheet_path(self, address: Address, name: str):
        """Return the path to a sheet file for the given address and name."""
        return self.files_path(address, FileType.META) / f"{name}.parquet"

    def files_path(self, address, file_type):
        """Return the path to the files directory for a given address and type."""
        return self.as_path(
            self.base_data if file_type == FileType.DATA else self.base_meta,
            address,
        )


def fs_data_store(base: Path = Path("datastore")):
    """A filesystem-backed data store rooted at ``base``."""
    return FSDataStore(
        base_data=base / "data",
        base_meta=base / "meta",
        base_cache=base / "cache",
        base_global=base / "global",
    )
