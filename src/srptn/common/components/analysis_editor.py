"""Editing an Analysis' workflow contract and declared tables.

``workflow_picker`` selects a published ``Workflow`` and deploys its pinned
upstream; ``analysis_editor`` then edits the runner-facing config and each
declared table (via :mod:`sample_table`), returning the ``TableConvert`` plans to
build them at store time.
"""

from typing import TYPE_CHECKING

import streamlit as st

from ..access.store import AccessStore
from ..accounts.policy import Actor
from ..data import Address
from ..data.entities.analysis import WorkflowManager
from ..data.entities.workflow import Workflow
from ..data.fs import FSDataStore
from ..utils.schema_inference import infer_schema, update_schema
from ..utils.snakedeploy import CachedWorkflowManager
from ..utils.workflow_tables import TableSpec, tables_from_data
from ..utils.yaml_utils import load_yaml
from .config_editor import ace_config_editor, create_form
from .sample_table import sample_table_editor
from .workflow_source import _SELECTED_MANAGER

if TYPE_CHECKING:
    import polars as pl
    from ..transform.convert import TableConvert

_SELECTED_WORKFLOW = "workflow-selected-entity"


def workflow_picker(
    access: AccessStore,
    actor: Actor,
    address: Address,
    data_store: FSDataStore,
):
    """Pick a readable curated Workflow and deploy its pinned upstream on demand.

    Returns ``(workflow, manager)`` once a workflow is selected, where
    ``manager`` is ``None`` until its upstream has been deployed.
    """
    workflows = access.entities(actor, Workflow)
    if not workflows:
        st.warning("No Workflow found")
        return
    names = {str(workflow.address): workflow for workflow in workflows}
    selected = st.selectbox(
        "Select workflow", names, index=None, key="workflow-select-source"
    )
    if selected is None:
        return
    workflow = names[selected]
    if st.session_state.get(_SELECTED_WORKFLOW) == str(workflow.address):
        return workflow, st.session_state.get(_SELECTED_MANAGER)
    if st.button("Deploy", key="workflow-select-deploy"):
        return workflow, _deploy_curated(workflow, access, actor, address, data_store)
    return workflow, None


def _deploy_curated(
    workflow: Workflow,
    access: AccessStore,
    actor: Actor,
    address: Address,
    data_store: FSDataStore,
):
    """Deploy a curated workflow's pinned upstream into the analysis workspace."""
    for key in list(st.session_state):
        if isinstance(key, str) and key.startswith("workflow-config-"):
            del st.session_state[key]
    workspace = access.workspace(actor, address)
    cached = CachedWorkflowManager(data_store)
    manager = WorkflowManager.deploy(workspace, workflow.upstream.version, cached)
    if manager is not None:
        st.session_state[_SELECTED_MANAGER] = manager
        st.session_state[_SELECTED_WORKFLOW] = str(workflow.address)
    return manager


def analysis_editor(workflow: Workflow, tables: dict[str, pl.DataFrame]):
    """Edit a curated workflow's runner-facing config and declared tables.

    The ``Workflow`` contract is authoritative: config/schema come from the
    entity (never the deployed repository), the config never loads workspace
    files, and the declared tables are built in memory and written only at
    store time.  Each declared table is generated from the Datasets' long tables
    (one editor per file) and returned as a ``TableConvert``.

    :returns: ``(config, converts)`` -- the edited config mapping and the
        ``{target: TableConvert}`` mapping.
    """
    config_viewer = st.radio(
        "Configuration editor mode",
        ["Form", "Text Editor"],
        horizontal=True,
    )

    st.divider()
    if st.session_state.get("workflow-config-form") is None:
        config: dict = load_yaml(workflow.config) or {}
        if not isinstance(config, dict):
            st.error("Workflow configuration must be a YAML mapping.")
            return config, None
        schema = load_yaml(workflow.config_schema) or {}
        final_schema = update_schema(schema, config) if schema else infer_schema(config)
        st.session_state["workflow-config-form"] = config
        st.session_state["workflow-config-form-schema"] = final_schema
        st.session_state["workflow-config-form-valid"] = {}
    else:
        config = st.session_state["workflow-config-form"]
        final_schema = st.session_state["workflow-config-form-schema"]

    if config_viewer == "Form":
        create_form(config, final_schema, "workflow-config-")
    else:
        parsed = ace_config_editor(config, final_schema)
        if parsed is not None:
            config = st.session_state["workflow-config-form"] = parsed

    key = f"workflow-analysis-{workflow.address}"
    tables_key = f"{key}-tables"
    if tables_key not in st.session_state:
        st.session_state[tables_key] = tables_from_data(workflow.tables)
    specs = st.session_state[tables_key]
    return config, _declared_tables(key, config, specs, tables)


def _declared_tables(
    key: str,
    config,
    specs: dict[str, TableSpec],
    tables: dict[str, pl.DataFrame],
):
    """Render each declared table path as its own :class:`TableConvert` editor.

    Config fields that resolve to the same file share one declaration; every
    distinct file path is built separately, so the result is keyed by path.  A
    path may only carry one row schema: two declarations that disagree are a
    contract error and are refused rather than silently overwritten.  The row
    schema stays read-only -- it is part of the curated contract -- and is
    checked against the generated preview while editing.
    """
    by_path: dict[str, TableSpec] = {}
    for spec in specs.values():
        for field in spec.fields:
            paths = TableSpec([field], spec.schema, spec.example).paths(config)
            if not paths:
                continue
            path = paths[0]
            group = by_path.get(path)
            if group is None:
                by_path[path] = TableSpec([field], spec.schema, spec.example)
            elif group.schema != spec.schema:
                st.error(
                    f"Conflicting schemas declared for {path}: "
                    f"{'.'.join(map(str, group.fields[0]))} and "
                    f"{'.'.join(map(str, field))} disagree. "
                    "A file can only have one row schema."
                )
                st.stop()
            else:
                by_path[path] = TableSpec(
                    [*group.fields, field], group.schema, group.example
                )
    if by_path:
        st.markdown("Edit tables")
    converts: dict[str, TableConvert] = {}
    for path, spec in by_path.items():
        fields_label = ", ".join(".".join(map(str, field)) for field in spec.fields)
        st.caption(f"Edit {path}, referenced fields: {fields_label}")
        convert = sample_table_editor(f"{key}-{path}", tables, spec.schema)
        if convert is not None:
            converts[path] = convert
    return converts
