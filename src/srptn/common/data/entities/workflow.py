"""Curated workflows: an owner-authored wrapper around an upstream workflow.

A ``Workflow`` is a first-class entity like ``Dataset`` and ``Analysis``: it is
owned, stored in the data store and published through the same visibility
mechanism.  Its content is the curation contract -- the pinned upstream
reference (version + internal schema), the runner-facing config and schema, the
table sidecar (declared tables with row schemas and examples) and the top-level
``code`` that converts the runner config into the upstream config.  The deployed
Snakefile is left untouched; the platform runs the code to produce the config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import streamlit as st
import yaml

from .. import DataStore, Entity
from ...utils.snakedeploy import Version
from ...utils.workflow_tables import tables_from_data

UPSTREAM_FILE = "upstream.yml"
CONFIG_FILE = "config.yaml"
CONFIG_SCHEMA_FILE = "config.schema.yaml"
TABLES_FILE = "tables.yaml"
CODE_FILE = "config_code.py"


class UpstreamRef(NamedTuple):
    """A pinned upstream reference: URL/commit and the internal schema."""

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
    code: str
    tables: str = ""

    def show(self, actor, access):
        """Display the curated contract (already authorized)."""
        st.header(self.address, divider=True)
        st.markdown(self.desc)
        st.markdown(f"remote url: {self.upstream.version}")
        st.code(self.config_schema, language="yaml")
        if access.can_write(actor, self.address):
            with st.expander("Config conversion code"):
                st.code(self.code, language="python")
            with st.expander("Upstream internal schema (validation reference)"):
                st.code(self.upstream.schema, language="yaml")
            for identifier, spec in tables_from_data(self.tables).items():
                with st.expander(f"Example table {identifier}:"):
                    st.markdown("used fields:")
                    for field in spec.fields:
                        st.markdown("- " + ".".join(f"**{i}**" for i in field))
                    st.dataframe(spec.example_table, use_container_width=True)
                    st.code(
                        yaml.safe_dump(spec.schema, sort_keys=False),
                        language="yaml",
                    )

    @classmethod
    def load(cls, data_store: DataStore, address):
        """Load a curated workflow from the data store."""
        workspace = data_store.workspace(address)
        details = yaml.safe_load(workspace.read_meta(UPSTREAM_FILE))
        return cls(
            address=address,
            desc=workspace.desc,
            upstream=UpstreamRef.from_dict(details),
            config=workspace.read_meta(CONFIG_FILE),
            config_schema=workspace.read_meta(CONFIG_SCHEMA_FILE),
            code=workspace.read_meta(CODE_FILE),
            tables=workspace.read_meta(TABLES_FILE, ""),
        )

    def store(self, data_store: DataStore):
        """Persist the curated contract in the data store."""
        workspace = data_store.workspace(self.address)
        workspace.store_desc(self.desc)
        upstream = yaml.safe_dump(self.upstream.to_dict(), sort_keys=False)
        workspace.write_meta(UPSTREAM_FILE, upstream)
        workspace.write_meta(CONFIG_FILE, self.config)
        workspace.write_meta(CONFIG_SCHEMA_FILE, self.config_schema)
        workspace.write_meta(CODE_FILE, self.code)
        workspace.write_meta(TABLES_FILE, self.tables)
