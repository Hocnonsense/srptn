import streamlit as st

from .config_editor import ace_config_editor, config_editor
from .schemas import infer_schema, update_schema
from .ui_components import persistent_text_input
from ..data import Address, DataStore
from ..data.entities.analysis import WorkflowManager


def workflow_selector(
    address: Address,
    data_store: DataStore,
):
    """Create a workflow selector widget in Streamlit with persistent text inputs.

    :return: The selected workflow or None if the input is incomplete.
    """

    @st.cache_data(show_spinner="Fetching workflow from API...")
    def get_workflow(
        url: str | None,
        tag: str | None,
        branch: str | None,
        *,
        refresh: bool,
    ):
        # FIXME: ensure_workflow to avoid @st.cache_data
        # If the workflow is already stored at data_store / address,
        # then do not store again.
        # TODO: what if the workflow exists with a different URL, tag, or branch
        if url and (tag or branch):
            for key in st.session_state:
                key: str
                if key.startswith("workflow-config-"):
                    del st.session_state[key]
            # old tempdir is deleted -> re-caching the workflow
            st.session_state["workflow-refresh"] = not refresh

            workflow_manager = WorkflowManager(url, tag, branch, data_store, address)
            workflow_manager.store()
            return workflow_manager
        st.info("Please provide a workflow URL with a tag or branch")

    url = persistent_text_input(
        "Workflow repository URL (e.g. https://github.com/snakemake-workflows/rna-seq-kallisto-sleuth, "
        "you can also explore from "
        "the [catalog](https://snakemake.github.io/snakemake-workflow-catalog/docs/all_standardized_workflows.html))",
        "workflow-meta-url",
        "https://github.com/snakemake-workflows/rna-seq-kallisto-sleuth",
    )
    # TODO: pre-load the url to enable the user to select tag/branch/commit
    tag = persistent_text_input(
        "Workflow repository tag (optional)",
        "workflow-meta-tag",
        "Enter tag",
    )

    branch = persistent_text_input(
        "Workflow repository branch (optional)",
        "workflow-meta-branch",
        "Enter branch",
    )
    if "workflow-refresh" not in st.session_state:
        st.session_state["workflow-refresh"] = False
    return get_workflow(url, tag, branch, refresh=st.session_state["workflow-refresh"])


def workflow_editor(workflow_manager: WorkflowManager):
    """Create and edit the configuration of a workflow.

    :param workflow: The workflow object containing URL, tag, and branch information.
    :return: The temporary directory where the workflow is deployed.
    """
    config_viewer = st.radio(
        "Configuration editor mode",
        ["Form", "Text Editor"],
        horizontal=True,
    )

    st.divider()
    if not st.session_state.get("workflow-config-form"):
        st.session_state["workflow-config-form"] = workflow_manager.get_config()
        st.session_state["workflow-config-form-schema"] = workflow_manager.get_schema(
            "config",
        )
        config = st.session_state["workflow-config-form"]
        config_schema = st.session_state["workflow-config-form-schema"]
        if config_schema:
            final_schema = update_schema(config_schema, config)
        else:
            final_schema = infer_schema(config)
        st.session_state["workflow-config-form-valid"] = {}
    else:
        config = st.session_state["workflow-config-form"]
        final_schema = st.session_state["workflow-config-form-schema"]

    if config_viewer == "Form":
        config_editor(config, final_schema, workflow_manager)
    else:
        ace_config_editor(config, final_schema, workflow_manager)
