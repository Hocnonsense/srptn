import streamlit as st

from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor, Role
from srptn.common.components.analysis_editor import (
    analysis_editor,
    workflow_picker,
)
from srptn.common.components.dataset_inputs import (
    dataset_long_table,
    keyed_tables,
    make_key,
    make_realpath,
)
from srptn.common.components.entities import data_selector
from srptn.common.components.forms import entity_meta_editor
from srptn.common.data.entities.analysis import Analysis
from srptn.common.data.fs import fs_data_store
from srptn.views import PageInfo


def _fields_invalid():
    validation: dict = st.session_state.get("workflow-config-form-valid", {})
    invalid_fields = [key for key, value in validation.items() if value is False]
    if invalid_fields:
        st.error(f"The following fields are incorrect: {', '.join(invalid_fields)}")
        return True


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

    config, converts = analysis_editor(workflow, keyed_tables(tables, make_key))
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
            final = keyed_tables(tables, make_realpath(data_store.workspace(address)))
            files, errors = workflow.generate_files(
                config, converts, final, address, data_store
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
