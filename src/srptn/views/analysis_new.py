import streamlit as st

from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor
from srptn.common.components.categories import category_editor
from srptn.common.components.descriptions import desc_editor
from srptn.common.components.entities import data_selector
from srptn.common.components.ui_components import persistent_text_input
from srptn.common.components.workflows import workflow_editor, workflow_selector
from srptn.common.data import Address, DataStore
from srptn.common.data.entities.analysis import Analysis, WorkflowManager
from srptn.common.data.entities.dataset import Dataset
from srptn.common.data.fs import fs_data_store


def store_analysis(
    address: Address,
    desc: str,
    datasets: list[Dataset],
    workflow_manager: WorkflowManager,
    data_store: DataStore,
):
    """Store the analysis."""
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
    if valid:
        Analysis(
            address=address,
            desc=desc,
            datasets=datasets,
            workflow_manager=workflow_manager,
        ).store(data_store)
        st.success(f"Stored analysis {address}")


def page_new_analysis(actor: Actor):
    data_store = fs_data_store()
    access = AccessStore(data_store)

    categories = category_editor("workflow-meta")

    analysis_name = persistent_text_input(
        "Analysis name",
        "workflow-meta-name",
        "Enter name",
    )

    render_continue = True
    address = Address(actor.id, Analysis, categories=categories, name=analysis_name)
    if data_store.occupied(address, only_check_meta=True):
        st.error(f"Analysis {address} already exists")
        render_continue = False

    if render_continue:
        desc = desc_editor("workflow-meta")

        datasets = data_selector(access, actor, "workflow-meta-datasets")

        if not categories or not analysis_name:
            render_continue = False

    if not render_continue:
        st.stop()

    workflow_manager = workflow_selector(
        access, actor, address, data_store
    )

    if workflow_manager is not None:
        workflow_editor(workflow_manager)
        if st.button("Store", disabled=(not desc) or (not analysis_name)):
            # Re-check authority at the write itself (the page guard is not a
            # substitute for an operation-level check).
            if not access.can_run(actor, address):
                st.error("You do not have permission to store this analysis.")
                st.stop()
            store_analysis(address, desc, datasets, workflow_manager, data_store)
