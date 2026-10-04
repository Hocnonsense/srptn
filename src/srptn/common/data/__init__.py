import io
import re
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Iterable, Self, BinaryIO, TypeVar
from pathlib import Path

import polars as pl


@dataclass
class Address:
    """
    Represents an address composed of owner, entity type, categories, and name.

    Identify a workdir of a workflow
    """

    owner: str
    entity_type: type["Entity"]
    categories: list[str]
    name: str

    @classmethod
    def from_str(cls, value: str):
        """Parse an address from a string."""
        from .entities import _entity_types

        owner, entity, *categories, name = value.split("/")
        entity = _entity_types[entity]
        return cls(owner=owner, entity_type=entity, categories=categories, name=name)

    @classmethod
    def from_filename(cls, filename: str):
        """Parse an address from a filename."""
        if not filename or "___" not in filename:
            raise ValueError("Invalid filename format")
        return cls.from_str(re.sub(r"___", "/", filename))

    def to_filename(self):
        """Convert the address to a filename-safe format."""
        if "/" not in str(self):
            raise ValueError("Invalid address format")
        return re.sub(r"/", "___", str(self))

    def __str__(self):
        """Return the address as a formatted string."""
        return f"{self.owner}/{self.entity_type.__name__.lower()}/{'/'.join(self.categories)}/{self.name}"


@dataclass
class Entity(ABC):
    """Abstract base class for entities with an address and description."""

    address: Address
    desc: str

    def __post_init__(self):
        """Validate the entity type against the address."""
        if self.address.entity_type != self.__class__:
            raise ValueError(f"Address type must be '{self.__class__.__name__}'")

    @abstractmethod
    def show(self) -> None:
        """Abstract method to display entity information."""
        ...

    @classmethod
    @abstractmethod
    def load(cls, data_store: "DataStore", address: Address) -> Self:
        """Abstract method to load an entity from a data store."""

    def __str__(self):
        """Return the string representation of the entity."""
        return str(self.address)

    def __eq__(self, other):
        """Check equality based on class and address."""
        if not isinstance(other, Entity):
            raise NotImplementedError("Cannot compare Entity with non-Entity type")
        return self.__class__ == other.__class__ and self.address == other.address


class FileType(Enum):
    """Enum representing different file types."""

    DATA = "data"
    META = "meta"


E = TypeVar("E", bound=Entity)
T = TypeVar("T")


@dataclass(slots=True)
class DataStore(ABC):
    """Abstract base class for data stores."""

    @abstractmethod
    def cache_entries(
        self, owner: str | None = None, filter: Callable[[Path], T | None] = lambda x: x
    ) -> Iterable[tuple[T, datetime]]:
        """List undated cache entry directories without refreshing their timestamps."""
        ...

    @abstractmethod
    def cache_access(
        self, address: Address | str, timestamp: datetime | None = None, replace=False
    ) -> AbstractContextManager[Path]:
        """Create or locate a cache entry and exclusively use it until context exit.

        Cleanup must skip active entries and replacement must refuse them.
        Access fails immediately when a required lock is busy; never wait or retry.
        Replacement of an Address also moves its entity data/meta into the entry.
        Undated entries expire by last access; dated entries expire by timestamp.
        Refresh the access marker on entry and exit, including failed uses.
        The returned path is protected only for the duration of this context.
        """
        ...

    def clean_cache(self, before: timedelta) -> None:
        """Delete expired cache branches; before is their maximum age."""
        raise NotImplementedError()

    @abstractmethod
    def clean(self, address: Address) -> None:
        """Abstract method to clean data for a given address."""
        ...

    @abstractmethod
    def load_sheet(self, address: Address, sheet_name: str) -> pl.DataFrame:
        """Abstract method to load a sheet from the data store."""
        ...

    @abstractmethod
    def has_sheet(self, address: Address, sheet_name: str) -> bool:
        """Abstract method to check if a sheet exists in the data store."""
        ...

    @abstractmethod
    def load_desc(self, address: Address) -> str:
        """Abstract method to load a description from the data store."""
        ...

    @abstractmethod
    def load_file(
        self,
        address: Address,
        file_path: str,
        file_type: FileType,
    ) -> BinaryIO:
        """Abstract method to load a file from the data store."""
        ...

    @abstractmethod
    def has_file(
        self,
        address: Address,
        file_path: str,
        file_type: FileType,
    ) -> bool:
        """Abstract method to check if a file exists in the data store."""
        ...

    @abstractmethod
    def list_files(self, address: Address, file_type: FileType) -> pl.DataFrame:
        """Abstract method to list files in the data store."""
        ...

    @abstractmethod
    def store_file(
        self,
        address: Address,
        file: io.IOBase,
        file_path: str,
        file_type: FileType,
    ) -> None:
        """Abstract method to store a file in the data store."""
        ...

    @abstractmethod
    def store_desc(self, address: Address, desc: str) -> None:
        """Abstract method to store a description in the data store."""
        ...

    @abstractmethod
    def store_sheet(
        self,
        address: Address,
        sheet: pl.DataFrame,
        sheet_name: str,
    ) -> None:
        """Abstract method to store a sheet in the data store."""
        ...

    @abstractmethod
    def entities(
        self,
        entity_type: type[E],
        search_term: str | None = None,
        only_owned_by: str | None = None,
    ) -> list[E]:
        """Abstract method to fetch entities from the data store."""
        ...

    @abstractmethod
    def occupied(self, address: Address) -> bool:
        """Abstract method to check if the address is used by an Entity."""
        ...

    @abstractmethod
    def files_path(self, address: Address, file_type: FileType) -> Path:
        """Abstract method to get the path for files of a specific type."""
        ...
