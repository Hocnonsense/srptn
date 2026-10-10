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
from ..utils.schema_validation import schema_errors, validation_errors
from ..utils.snakedeploy import Version
from ..utils.workflow_preview import PreviewResult
from ..utils.workflow_tables import (
    TableSpec,
    add_table_fields,
    build_tables,
    tables_from_data,
    tables_to_data,
)
from ..utils.yaml_utils import dump_yaml, load_yaml, parse_yaml
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
        config_dict = load_yaml(config_text) or {}
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

    config, config_error = parse_yaml(config_text)
    parsed_runner, runner_error = parse_yaml(runner_schema_text)
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
    schema_messages = schema_errors(runner_schema)
    for message in schema_messages:
        with col2:
            st.error(f"Schema error: {message}")
    if isinstance(config, dict) and not schema_messages:
        messages = validation_errors(config, runner_schema)
        for message in messages:
            st.error(message)
        if not messages:
            st.success("Config matches the schema.")

    workspace = data_store.workspace(init_state.address)
    tables = st.session_state[tables_dict_key]
    if isinstance(config, dict):
        _tables_section(
            f"{key}-tables-{run}",
            config,
            tables,
            workspace.data_path,
            f"{key}-table-editor-{run}",
        )

    st.markdown("**Config conversion code** — `config` in, converted `config` out")
    code = st_ace(
        _DEFAULT_CODE,
        language="python",
        height=200,
        auto_update=False,
        key=f"{key}-code-{run}",
    )

    internal_schema, _ = parse_yaml(init_state.internal_schema_text)
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


def _tables_section(
    key: str, config, tables: dict[str, TableSpec], data_path: Path, editor_key: str
):
    """List declared tables as paired forms, each with edit/delete, then ``+``."""
    st.markdown("**Declared tables** — editable example (left) vs row schema (right)")
    for name in list(tables):
        spec = tables[name]
        heads = st.columns([8, 1, 1])
        heads[0].markdown(f"`{name}`")
        if heads[1].button(
            "",
            icon=":material/edit:",
            help="Edit this table's config binding",
            key=f"{key}-{name}-edit",
        ):
            _open_table_form(
                key,
                "edit",
                name=name,
                path=list(spec.fields[0]) if spec.fields else None,
            )
        if heads[2].button(
            "",
            icon=":material/remove:",
            help="Delete this table",
            key=f"{key}-{name}-delete",
        ):
            tables.pop(name, None)
            st.rerun()
        tables[name] = table_schema_editor(
            editor_key, name, tables[name], tables[name].paths(config)
        )
    if st.button("", icon=":material/add:", help="Define a table", key=f"{key}-add"):
        _open_table_form(key, "add")
    _table_form(key, config, tables, data_path)


def _open_table_form(key: str, mode: str, name: str | None = None, path=None):
    """Open the cascading config-key picker for adding or editing a table."""
    seq = st.session_state.get(f"{key}-form-seq", 0) + 1
    st.session_state[f"{key}-form-seq"] = seq
    st.session_state[f"{key}-form"] = {
        "mode": mode,
        "name": name,
        "path": path,
        "seq": seq,
    }


def _table_form(key: str, config, tables: dict[str, TableSpec], data_path: Path):
    """Render the open config-key picker; Save is enabled once a value is a string."""
    form = st.session_state.get(f"{key}-form")
    if not form:
        return
    seq = form["seq"]
    prefill = form.get("path")
    st.markdown("**Define table** — pick a config key until it resolves to a file")

    node = config
    path: list[str] = []
    level = 0
    while isinstance(node, dict) and node:
        options = list(node)
        widget_key = f"{key}-form-{seq}-L{level}"
        if (
            widget_key in st.session_state
            and st.session_state[widget_key] not in options
        ):
            del st.session_state[widget_key]
        if (
            prefill
            and level < len(prefill)
            and prefill[level] in options
            and widget_key not in st.session_state
        ):
            st.session_state[widget_key] = prefill[level]
        choice = st.selectbox(f"key {level}", options, key=widget_key)
        if choice is None:
            break
        path.append(choice)
        node = node[choice]
        level += 1

    value = node if isinstance(node, str) and node else None
    if value:
        st.caption(f"{'.'.join(path)} -> {value}")

    save_col, cancel_col = st.columns(2)
    if save_col.button(
        "Save",
        key=f"{key}-form-save-{seq}",
        disabled=value is None,
        type="primary",
    ):
        _save_table_form(key, form, path, config, tables, data_path)
    if cancel_col.button("Cancel", key=f"{key}-form-cancel-{seq}"):
        st.session_state.pop(f"{key}-form", None)
        st.rerun()


def _save_table_form(
    key: str,
    form,
    path: list[str],
    config,
    tables: dict[str, TableSpec],
    data_path: Path,
):
    """Persist the picked path; in edit mode replace the table's old binding."""
    if form["mode"] == "edit" and form.get("name") in tables:
        spec = tables[form["name"]]
        old = form.get("path")
        remaining = [field for field in spec.fields if field != old]
        if remaining:
            tables[form["name"]] = TableSpec(remaining, spec.schema, spec.example)
        else:
            tables.pop(form["name"], None)
    add_table_fields(config, path, tables, data_path)
    st.session_state.pop(f"{key}-form", None)
    st.rerun()


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
