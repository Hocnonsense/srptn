"""The entity model and the low-level data-store capability.

``Address``, ``Entity`` and ``FileType`` are the backend-independent model.
``DataStore`` is the low-level, backend-agnostic content capability (meta and
files, read and write); it is not exposed to the application directly — the
authorized ``AccessStore`` is.
"""

from __future__ import annotations

import io

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, BinaryIO, Self, TypeVar

if TYPE_CHECKING:
    import polars as pl

    from ..accounts.policy import Actor
    from ..access.store import AccessStore
    from .workspace import Workspace


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

    def can_run(self, actor: "Actor", access: "AccessStore | None"):
        """Check if the actor can run/stop this entity."""
        return access is not None and access.can_run(actor, self.address)

    @abstractmethod
    def show(self, actor: "Actor", access: "AccessStore") -> None:
        """Display the entity.

        The entity is already authorized (it came from ``AccessStore``), so its
        own data needs no further check; ``access`` is only required for
        actor-level actions such as running an analysis.
        """
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


class DataStore(ABC):
    """Low-level content capability: entity meta and files, read and write.

    Backend-agnostic and *not* exposed to the application.  The local
    workspace is a filesystem-only capability reached through
    :meth:`workspace`; the cache stays internal to the filesystem backend.
    """

    @abstractmethod
    def load_global_meta(self, name: str) -> bytes | None: ...

    @abstractmethod
    def store_global_meta(self, name: str, data: bytes) -> None: ...

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
        *,
        owned_by: str | None = None,
    ) -> list[E]: ...

    @abstractmethod
    def occupied(self, address: Address, only_check_meta: bool = False) -> bool:
        """Check address occupancy, ignoring draft data when only_check_meta is true."""
        ...

    @abstractmethod
    def workspace(self, address: Address) -> Workspace:
        """A locked local working directory for ``address`` (filesystem only)."""
