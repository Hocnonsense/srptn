"""Streamlit editor for the publisher (workflow curation) flow.

Renders the external config/schema, the ``parse_config`` body, tests the
transformation against the upstream schema, and persists a :class:`Workflow`
entity.  All heavy lifting is in :mod:`..utils.workflow_curation`.
"""

from __future__ import annotations

from typing import NamedTuple

import streamlit as st
import yaml
from streamlit_ace import st_ace

from srptn.common.data import Address, DataStore

from ..data.entities.workflow import UpstreamRef, Workflow
from ..utils.snakedeploy import Version
from ..utils.workflow_curation import (
    load_yaml,
    rewrite_snakefile,
    transform_errors,
    wrap_parse_config,
)

_ACE_HEIGHT = 360


class DeployInitialState(NamedTuple):
    address: Address
    version: Version
    config: str
    schema: str
    snakefile: str


def workflow_editor(
    key: str,
    *,
    init_state: DeployInitialState,
    desc: str,
    data_store: DataStore,
):
    """Render the curation editors and persist the workflow on confirmation."""
    run = st.session_state.get(f"{key}-run", 0)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**External config** (runner-facing)")
        config_text = st_ace(
            init_state.config,
            language="yaml",
            height=_ACE_HEIGHT,
            auto_update=False,
            key=f"{key}-config-{run}",
        )
    with col2:
        st.markdown("**External schema** (runner-facing)")
        schema_text = st_ace(
            init_state.schema,
            language="yaml",
            height=_ACE_HEIGHT,
            auto_update=False,
            key=f"{key}-schema-{run}",
        )

    st.markdown("**parse_config body** - `config` in, transformed config out")
    body = st_ace(
        "return config",
        language="python",
        height=200,
        auto_update=False,
        key=f"{key}-body-{run}",
    )

    with st.expander("Upstream internal schema (validation reference)"):
        st.code(init_state.schema, language="yaml")

    def parse_inputs():
        try:
            return (
                load_yaml(config_text),
                load_yaml(schema_text),
                load_yaml(init_state.schema),
            ), []
        except yaml.YAMLError as error:
            return None, [f"YAML error: {error}"]

    if st.button("Test transformation", key=f"{key}-test-{run}"):
        parsed, parse_errors = parse_inputs()
        transformed = None
        if parsed:
            # TODO: show transformed, not just errors
            transformed, errors = transform_errors(body, *parsed)
            parse_errors += errors
        st.session_state[f"{key}-errors-{run}"] = parse_errors
        st.session_state[f"{key}-transformed-{run}"] = transformed

    errors = st.session_state.get(f"{key}-errors-{run}")
    if errors is not None:
        for message in errors:
            st.error(message)
        if not errors:
            st.success("Transformation valid against the upstream internal schema.")

    if st.button("Save workflow", key=f"{key}-save-{run}"):
        parsed, parse_errors = parse_inputs()
        if not parsed:
            for message in parse_errors:
                st.error(message)
            return
        _, errors = transform_errors(body, *parsed)
        if errors:
            for message in errors:
                st.error(message)
            return
        Workflow(
            address=init_state.address,
            desc=desc,
            upstream=UpstreamRef(version=init_state.version, schema=init_state.schema),
            config=config_text,
            config_schema=schema_text,
            parse_config=wrap_parse_config(body),
            snakefile=rewrite_snakefile(init_state.snakefile),
        ).store(data_store)
        st.session_state[f"{key}-saved"] = str(init_state.address)
        st.success(f"Saved workflow {init_state.address}")
