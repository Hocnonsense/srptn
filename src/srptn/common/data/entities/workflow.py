"""Curated workflows: an owner-authored wrapper around an upstream workflow.

A ``Workflow`` is a first-class entity like ``Dataset`` and ``Analysis``: it is
owned, stored in the data store and published through the same visibility
mechanism.  Its content is the curation contract -- the pinned upstream
reference, the external (runner-facing) config and schema, the
``parse_config`` transformation, the generated wrapper ``Snakefile`` and the
upstream internal schema kept as a validation reference.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

import streamlit as st
import yaml


from .. import DataStore, Entity, FileType
from ...utils.snakedeploy import Version

if TYPE_CHECKING:
    from ..workspace import Workspace

UPSTREAM_FILE = "upstream.yml"
CONFIG_FILE = "config.yaml"
CONFIG_SCHEMA_FILE = "config.schema.yaml"
PARSE_CONFIG_FILE = "parse_config.py"
SNAKEFILE_FILE = "Snakefile"


def write_meta(workspace: Workspace, name: str, text: str):
    """Store a text artifact under the workspace's meta files."""
    workspace.store_file(io.BytesIO(text.encode()), name, FileType.META)


def read_meta(workspace: Workspace, name: str):
    """Read a text artifact stored by :func:`write_meta`."""
    with workspace.load_file(name, FileType.META) as handle:
        return handle.read().decode()


class UpstreamRef(NamedTuple):
    """A pinned upstream reference: URL and commit hash."""

    version: Version
    schema: str | None = None

    def to_dict(self):
        """Convert to a dict for YAML serialization."""
        return {
            "upstream_ref": self.version._asdict(),
            "upstream_schema": self.schema,
        }

    @classmethod
    def from_dict(cls, data: dict):
        """Create an UpstreamRef from a dict (as produced by to_dict)."""
        version = Version(**data.get("upstream_ref", {}))
        return cls(version=version, schema=data.get("upstream_schema"))


@dataclass
class Workflow(Entity):
    """A curated workflow wrapping an upstream repository at a pinned commit."""

    upstream: UpstreamRef
    config: str
    config_schema: str
    parse_config: str
    snakefile: str

    def show(self, actor, access):
        """Display the curated contract (already authorized)."""
        st.subheader("Upstream")
        st.code(
            f"{self.upstream.version.url} @ {self.upstream.version.commit}",
            language="text",
        )
        st.caption(f"Snakemake module: {self.address.name}")
        st.subheader("Schema")
        st.code(self.config_schema, language="yaml")
        if access.can_write(actor, self.address):
            with st.expander("Convert config to upstream format"):
                st.code(self.parse_config, language="python")
            with st.expander("Upstream internal schema (validation reference)"):
                st.code(self.upstream.schema, language="yaml")

    @classmethod
    def load(cls, data_store: DataStore, address):
        """Load a curated workflow from the data store."""
        workspace = data_store.workspace(address)
        details = yaml.safe_load(read_meta(workspace, UPSTREAM_FILE))
        return cls(
            address=address,
            desc=workspace.load_desc(),
            upstream=UpstreamRef.from_dict(details),
            config=read_meta(workspace, CONFIG_FILE),
            config_schema=read_meta(workspace, CONFIG_SCHEMA_FILE),
            parse_config=read_meta(workspace, PARSE_CONFIG_FILE),
            snakefile=read_meta(workspace, SNAKEFILE_FILE),
        )

    def store(self, data_store: DataStore):
        """Persist the curated contract in the data store."""
        workspace = data_store.workspace(self.address)
        workspace.store_desc(self.desc)
        write_meta(
            workspace,
            UPSTREAM_FILE,
            yaml.safe_dump(self.upstream.to_dict(), sort_keys=False),
        )
        write_meta(workspace, CONFIG_FILE, self.config)
        write_meta(workspace, CONFIG_SCHEMA_FILE, self.config_schema)
        write_meta(workspace, PARSE_CONFIG_FILE, self.parse_config)
        write_meta(workspace, SNAKEFILE_FILE, self.snakefile)
