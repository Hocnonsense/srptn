import streamlit as st

from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor, Role
from srptn.common.components.entities import data_selector
from srptn.common.components.forms import entity_meta_editor
from srptn.common.components.workflows import workflow_editor, workflow_picker
from srptn.common.data import Address, DataStore
from srptn.common.data.entities.analysis import Analysis, WorkflowManager
from srptn.common.data.entities.dataset import Dataset
from srptn.common.data.entities.workflow import Workflow
from srptn.common.data.fs import fs_data_store
from srptn.common.utils.workflow_preview import PreviewResult
from srptn.common.utils.yaml_utils import load_yaml
from srptn.views import PageInfo


def generate_files(
    workflow: Workflow,
    config: dict,
    tables,
    address: Address,
    data_store: DataStore,
):
    """Convert the edited runner config into upstream files for the workspace."""
    internal_schema = (
        load_yaml(workflow.upstream.schema) if workflow.upstream.schema else None
    )
    schema_dir = data_store.workspace(address).data_path / "workflow" / "schemas"
    return PreviewResult.run(workflow.code, config, tables, internal_schema, schema_dir)


def store_analysis(
    address: Address,
    desc: str,
    datasets: list[Dataset],
    workflow_manager: WorkflowManager,
    workflow: Workflow,
    config: dict,
    tables,
    data_store: DataStore,
):
    """Store the analysis, applying the curated contract to the workspace."""
    valid = True
    if st.session_state.get("workflow-config-form-valid"):
        invalid_fields = [
            key
            for key, value in st.session_state.get(
                "workflow-config-form-valid", {}
            ).items()
            if value is False
        ]
        if invalid_fields:
            invalid_fields_str = ", ".join(invalid_fields)
            st.error(
                f"The following field {'s are' if len(invalid_fields) > 1 else ' is'}"
                f"incorrect: {invalid_fields_str}",
            )
            valid = False
    if not valid:
        return

    result = generate_files(workflow, config, tables, address, data_store)
    if not result.ok:
        for message in result.errors:
            st.error(message)
        return

    Analysis(
        address=address,
        desc=desc,
        datasets=datasets,
        workflow_manager=workflow_manager,
    ).store(data_store, files=result.files)
    st.success(f"Stored analysis {address}")


@PageInfo.wrap("New Analysis", Role.HOST)
def page_new_analysis(actor: Actor):
    data_store = fs_data_store()
    access = AccessStore(data_store)

    categories, analysis_name, desc = entity_meta_editor("workflow", "Analysis name")

    address = Address(actor.id, Analysis, categories=categories, name=analysis_name)
    if data_store.occupied(address, only_check_meta=True):
        st.error(f"Analysis {address} already exists")
        st.stop()

    if not categories or not analysis_name:
        st.stop()

    datasets = data_selector(access, actor, "workflow-meta-datasets")

    picked = workflow_picker(access, actor, address, data_store)
    if picked is None:
        return
    workflow, workflow_manager = picked
    if workflow_manager is None:
        return

    config, tables = workflow_editor(workflow)
    if st.button("Store"):
        # Re-check authority at the write itself (the page guard is not a
        # substitute for an operation-level check).
        if not access.can_run(actor, address):
            st.error("You do not have permission to store this analysis.")
            st.stop()
        # Never fail silently: a disabled button gives no feedback, so validate
        # here and report why storing cannot proceed.
        if not analysis_name:
            st.error("Analysis name is required before storing.")
            return
        if not desc:
            st.error("Analysis description is required before storing.")
            return
        try:
            store_analysis(
                address,
                desc,
                datasets,
                workflow_manager,
                workflow,
                config,
                tables,
                data_store,
            )
        except Exception as error:  # noqa: BLE001 - never store silently
            st.exception(error)
