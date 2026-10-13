from typing import Callable

import streamlit as st
import polars as pl

from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor, Role
from srptn.common.components.dataset_inputs import (
    dataset_long_table,
    make_key,
    make_realpath,
)
from srptn.common.components.entities import data_selector
from srptn.common.components.forms import entity_meta_editor
from srptn.common.components.sample_sheet import FILE_COLUMN
from srptn.common.components.workflows import workflow_editor, workflow_picker
from srptn.common.data import Address, DataStore
from srptn.common.data.entities.analysis import Analysis
from srptn.common.data.entities.workflow import Workflow
from srptn.common.data.fs import fs_data_store
from srptn.common.transform.convert import TableConvert
from srptn.common.utils.workflow_preview import run_tables
from srptn.common.utils.yaml_utils import load_yaml
from srptn.views import PageInfo


def generate_files(
    workflow: Workflow,
    config: dict,
    converts: dict[str, TableConvert],
    tables: dict[str, pl.DataFrame],
    address: Address,
    data_store: DataStore,
) -> tuple[dict[str, bytes], list[str]]:
    """Build each convert's table and run the workflow code.

    Returns ``(files, errors)``.
    """
    internal_schema = (
        load_yaml(workflow.upstream.schema) if workflow.upstream.schema else None
    )
    schema_dir = data_store.workspace(address).data_path / "workflow" / "schemas"
    provided = {}
    issues = []
    for target, convert in converts.items():
        provided[target] = convert.build(tables, issues)
    errors = [str(issue) for issue in issues]
    if errors:
        return {}, errors
    files, _ = run_tables(
        workflow.code, config, provided, internal_schema, schema_dir, errors
    )
    return files, errors


def _fields_invalid():
    validation: dict = st.session_state.get("workflow-config-form-valid", {})
    invalid_fields = [key for key, value in validation.items() if value is False]
    if invalid_fields:
        st.error(f"The following fields are incorrect: {', '.join(invalid_fields)}")
        return True


def _keyed_tables(
    tables: dict[str, pl.DataFrame],
    make_key: Callable[[str, pl.Expr], pl.Expr],
    file_column=FILE_COLUMN,
):
    """Stamp each table's ``file`` column with its key's address."""
    return {
        address: sheet.with_columns(
            make_key(address, pl.col(file_column)).alias(file_column)
        )
        for address, sheet in tables.items()
    }


@PageInfo.wrap("New Analysis", Role.HOST)
def page_new_analysis(actor: Actor):
    data_store = fs_data_store()
    access = AccessStore(data_store)

    address, desc = entity_meta_editor(
        "workflow",
        "Analysis name",
        actor,
        Analysis,
        data_store,
        only_check_meta=True,
    )

    datasets = data_selector(access, actor, "workflow-meta-datasets")
    tables = dataset_long_table("analysis-datasets", datasets)

    picked = workflow_picker(access, actor, address, data_store)
    if picked is None:
        return
    workflow, workflow_manager = picked
    if workflow_manager is None:
        return

    config, converts = workflow_editor(workflow, _keyed_tables(tables, make_key))
    if st.button("Store"):
        # Re-check authority at the write itself (the page guard is not a
        # substitute for an operation-level check).
        if not access.can_run(actor, address):
            st.error("You do not have permission to store this analysis.")
            st.stop()
        # Never fail silently: a disabled button gives no feedback, so validate
        # here and report why storing cannot proceed.
        if not desc:
            st.error("Analysis description is required before storing.")
            return
        if _fields_invalid():
            return
        try:
            final = _keyed_tables(tables, make_realpath(data_store.workspace(address)))
            files, errors = generate_files(
                workflow, config, converts, final, address, data_store
            )
            if errors:
                for message in errors:
                    st.error(message)
                return
            Analysis(
                address=address,
                desc=desc,
                datasets=datasets,
                workflow_manager=workflow_manager,
            ).store(data_store, files=files)
            st.success(f"Stored analysis {address}")
        except Exception as error:  # noqa: BLE001 - never store silently
            st.exception(error)
