"""The authorized facade over the low-level data store.

Every application access goes through :class:`AccessStore`; the underlying
:class:`~..data.DataStore` is never exposed.  Operations take ``(actor,
address)`` and are re-checked here.  ``workspace(actor, address)`` grants a
local :class:`~..data.workspace.Workspace` (filesystem backends only).
"""

from __future__ import annotations

from ..accounts.policy import Actor, Role
from ..data import Address, DataStore, E, FileType
from .public import PublicIndex


class AccessDenied(PermissionError):
    """Raised when an actor may not access a resource."""


class AccessStore:
    """Authorization and the only application-facing access to data."""

    def __init__(self, data_store: DataStore, index: PublicIndex | None = None):
        self._store = data_store
        self._index = index if index is not None else PublicIndex(data_store)

    # --- scope ----------------------------------------------------------

    def entities(
        self,
        actor: Actor,
        entity_type: type[E],
        search_term: str | None = None,
        *,
        only_owned: bool = False,
    ):
        """Entities the actor may browse (self plus public, or own only)."""
        own = self._store.entities(
            entity_type, search_term=search_term, owned_by=actor.id
        )
        if only_owned:
            return own
        public = [
            entity_type.load(self._store, address)
            for address in self._index.addresses(entity_type)
            if address.owner != actor.id
        ]
        if search_term:
            public = [
                entity
                for entity in public
                if search_term in str(entity.address) or search_term in entity.desc
            ]
        return own + public

    def can_read(self, actor: Actor, address: Address):
        return address.owner == actor.id or self._index.contains(address)

    def can_run(self, actor: Actor, address: Address):
        """Only the owner with a workflow-operator role may run/stop."""
        return address.owner == actor.id and actor.role >= Role.HOST

    def can_write(self, actor: Actor, address: Address):
        """Only the owner with a workflow-publisher role may write."""
        return address.owner == actor.id and actor.role >= Role.PUBLISHER

    def is_public(self, address: Address):
        return self._index.contains(address)

    # --- reads ----------------------------------------------------------

    def load_desc(self, actor: Actor, address: Address):
        self._require_read(actor, address)
        return self._store.load_desc(address)

    def load_sheet(self, actor: Actor, address: Address, sheet_name: str):
        self._require_read(actor, address)
        return self._store.load_sheet(address, sheet_name)

    def has_sheet(self, actor: Actor, address: Address, sheet_name: str):
        self._require_read(actor, address)
        return self._store.has_sheet(address, sheet_name)

    def load_file(
        self, actor: Actor, address: Address, file_path: str, file_type: FileType
    ):
        self._require_read(actor, address)
        return self._store.load_file(address, file_path, file_type)

    def list_files(self, actor: Actor, address: Address, file_type: FileType):
        self._require_read(actor, address)
        return self._store.list_files(address, file_type)

    # --- writes (owner only) --------------------------------------------

    def store_desc(self, actor: Actor, address: Address, desc: str):
        self._require_owner(actor, address)
        self._store.store_desc(address, desc)

    def store_sheet(self, actor: Actor, address: Address, sheet, sheet_name: str):
        self._require_owner(actor, address)
        self._store.store_sheet(address, sheet, sheet_name)

    def store_file(
        self, actor: Actor, address: Address, file, file_path: str, file_type: FileType
    ):
        self._require_owner(actor, address)
        self._store.store_file(address, file, file_path, file_type)

    # --- visibility -----------------------------------------------------

    def set_publish(self, actor: Actor, address: Address, publish: bool = True):
        self._require_owner(actor, address)
        if publish:
            self._index.publish(address)
        else:
            self._index.unpublish(address)

    # --- local workspace ------------------------------------------------

    def workspace(self, actor: Actor, address: Address):
        self._require_read(actor, address)
        return self._store.workspace(address)

    # --- helpers --------------------------------------------------------

    def _require_read(self, actor: Actor, address: Address):
        if not self.can_read(actor, address):
            raise AccessDenied(f"{actor.id} may not read {address}")

    def _require_owner(self, actor: Actor, address: Address):
        if address.owner != actor.id:
            raise AccessDenied(f"{actor.id} does not own {address}")
