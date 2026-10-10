"""Streamlit editor for the publisher (workflow curation) flow.

Layout: the runner-facing config and schema side by side (config live-checked
against the schema), then the declared tables (editable example on the left,
editable row schema on the right, with inline schema errors), then the
conversion code.  The runner schema and the table sidecar are separate
artifacts; the internal (upstream) schema is kept for validating the code
output.  "Preview conversion" runs the code over a temp copy of the examples,
validates the produced config and files against the upstream schemas, and only
then caches the ``Workflow`` and enables "Save workflow".
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import streamlit as st
import yaml
from streamlit_ace import st_ace


from ..data import Address, DataStore
from ..data.entities.workflow import UpstreamRef, Workflow
from ..utils.schema_inference import infer_schema
from ..utils.schema_validation import validation_errors
from ..utils.snakedeploy import Version
from ..utils.workflow_preview import PreviewResult
from ..utils.workflow_tables import (
    build_tables,
    tables_from_data,
    tables_to_data,
)
from ..utils.yaml_utils import dump_yaml, load_yaml
from .table_schema_editor import table_schema_editor

_ACE_HEIGHT = 340
_DEFAULT_CODE = (
    "# `config` holds the runner-facing config as a dict.\n"
    "# Reassign `config` to produce the upstream config.\n"
)


class DeployInitialState(NamedTuple):
    address: Address
    version: Version
    config_text: str
    runner_schema_text: str
    internal_schema_text: str
    tables_text: str

    @classmethod
    def from_workflow(
        cls,
        address: Address,
        version: Version,
        config: Path,
        schema: dict | None = None,
        data_path: Path | None = None,
    ):
        config_text = config.read_text()
        config_dict = load_yaml(config_text)
        internal = schema or infer_schema(config_dict)
        internal_text = dump_yaml(internal)
        tables_text = tables_to_data(build_tables(config_dict, data_path))
        return cls(
            address=address,
            version=version,
            config_text=config_text,
            runner_schema_text=internal_text,
            internal_schema_text=internal_text,
            tables_text=tables_text,
        )

    @property
    def upstream(self):
        """The upstream reference implied by the deploy-time fields."""
        return UpstreamRef(version=self.version, schema=self.internal_schema_text)


def workflow_editor(
    key: str, *, init_state: DeployInitialState, desc: str, data_store: DataStore
) -> Workflow | None:
    """Render the curation editors and persist the workflow on confirmation."""
    run = st.session_state.get(f"{key}-run", 0)
    schema_dict_key = f"{key}-runner-schema-dict"
    tables_dict_key = f"{key}-tables-dict"
    cached_key = f"{key}-workflow-{run}"

    if schema_dict_key not in st.session_state:
        st.session_state[schema_dict_key] = (
            load_yaml(init_state.runner_schema_text) or {}
        )
        st.session_state[tables_dict_key] = tables_from_data(init_state.tables_text)

    st.markdown(
        "**Runner-facing contract** — config (left) is checked against the "
        "schema (right)"
    )
    col1, col2 = st.columns(2)
    with col1:
        config_text = st_ace(
            init_state.config_text,
            language="yaml",
            height=_ACE_HEIGHT,
            auto_update=False,
            key=f"{key}-config-{run}",
        )
    with col2:
        runner_schema_text = st_ace(
            dump_yaml(st.session_state[schema_dict_key]),
            language="yaml",
            height=_ACE_HEIGHT,
            auto_update=False,
            key=f"{key}-runner-schema-{run}",
        )

    config, config_error = _parse(config_text)
    parsed_runner, runner_error = _parse(runner_schema_text)
    if (
        not runner_error
        and isinstance(parsed_runner, dict)
        and parsed_runner != st.session_state[schema_dict_key]
    ):
        st.session_state[schema_dict_key] = parsed_runner
    runner_schema = st.session_state[schema_dict_key]

    if config_error:
        with col1:
            st.error(config_error)
    if runner_error:
        with col2:
            st.error(runner_error)
    if runner_schema and isinstance(config, dict):
        messages = validation_errors(config, runner_schema)
        for message in messages:
            st.error(message)
        if not messages:
            st.success("Config matches the schema.")

    workspace = data_store.workspace(init_state.address)
    tables = st.session_state[tables_dict_key]
    if isinstance(config, dict) and tables:
        st.markdown(
            "**Declared tables** — editable example (left) vs row schema (right)"
        )
        editor_key = f"{key}-table-editor-{run}"
        for name, spec in tables.items():
            tables[name] = table_schema_editor(
                editor_key, name, spec, spec.paths(config)
            )

    st.markdown("**Config conversion code** — `config` in, converted `config` out")
    code = st_ace(
        _DEFAULT_CODE,
        language="python",
        height=200,
        auto_update=False,
        key=f"{key}-code-{run}",
    )

    internal_schema, _ = _parse(init_state.internal_schema_text)
    schema_dir = workspace.data_path / "workflow" / "schemas"

    if st.button(
        "Preview conversion",
        key=f"{key}-preview-{run}",
        disabled=not isinstance(config, dict) or runner_error is not None,
    ):
        result = PreviewResult.run(
            code, config, st.session_state[tables_dict_key], internal_schema, schema_dir
        )
        st.session_state[f"{key}-result-{run}"] = result
        if result.ok:
            # Only a clean preview caches the Workflow and enables Save.
            st.session_state[cached_key] = Workflow(
                address=init_state.address,
                desc=desc,
                upstream=init_state.upstream,
                config=config_text,
                config_schema=dump_yaml(runner_schema),
                code=code,
                tables=tables_to_data(st.session_state[tables_dict_key]),
            )
        else:
            st.session_state.pop(cached_key, None)

    _render_preview(st.session_state.get(f"{key}-result-{run}"))

    return st.session_state.get(cached_key)


def _render_preview(result: PreviewResult | None):
    st.markdown("**Generated config (read-only, checked against the upstream schema)**")
    if result is None:
        st.caption("Use 'Preview conversion' to generate the upstream config.")
        return
    if result.errors:
        for message in result.errors:
            st.error(message)
        return
    st.code(yaml.safe_dump(result.config, sort_keys=False), language="yaml")
    st.success("Preview valid: config and files match the upstream schemas.")
    if result.files:
        st.markdown("**Generated files**")
        for name, content in result.files.items():
            with st.expander(name):
                st.code(content.decode("utf-8", "replace"), language="text")


def _parse(text: str):
    try:
        return load_yaml(text), None
    except yaml.YAMLError as error:
        return None, f"YAML error: {error}"
