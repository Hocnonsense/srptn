import streamlit as st
import yaml

from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor
from srptn.common.components.categories import category_editor
from srptn.common.components.descriptions import desc_editor
from srptn.common.components.schemas import infer_schema
from srptn.common.components.ui_components import persistent_text_input
from srptn.common.components.workflow_editor import (
    DeployInitialState,
    workflow_editor,
)
from srptn.common.components.workflows import Version, select_workflow
from srptn.common.data import Address
from srptn.common.data.entities.analysis import WorkflowManager
from srptn.common.data.entities.workflow import Workflow
from srptn.common.data.fs import fs_data_store
from srptn.common.utils.snakedeploy import CachedWorkflowManager
from srptn.common.utils.workflow_curation import load_yaml
from srptn.common.utils.yaml_utils import CustomSafeDumper

_KEY = "publish-workflow"


def _deploy_upstream(
    access: AccessStore,
    actor: Actor,
    address: Address,
    cached: CachedWorkflowManager,
    version: Version,
):
    """Deploy the pinned upstream into the Workflow workspace and load its contract."""
    workspace = access.workspace(actor, address)
    manager = WorkflowManager.deploy(workspace, version, cached)
    if manager is None:
        return

    assert manager.config_path and manager.snakefile_path
    config_text = manager.config_path.read_text()
    schema = manager.get_schema("config") or infer_schema(load_yaml(config_text))
    schema_text = yaml.dump(schema, sort_keys=False, Dumper=CustomSafeDumper)
    st.session_state[f"{_KEY}-context"] = DeployInitialState(
        address=address,
        version=version,
        config=config_text,
        schema=schema_text,
        snakefile=manager.snakefile_path.read_text(),
    )
    st.session_state[f"{_KEY}-run"] = st.session_state.get(f"{_KEY}-run", 0) + 1


def page_new_workflow(actor: Actor):
    """Curate and publish a Workflow entity from a pinned upstream repository."""
    data_store = fs_data_store()
    access = AccessStore(data_store)

    st.header("Deploy Workflow", divider=True)
    col1, col2 = st.columns(2)
    with col1:
        categories = category_editor(f"{_KEY}-meta")
        name = persistent_text_input("Workflow name", f"{_KEY}-name", "Enter name")
    with col2:
        desc = desc_editor(f"{_KEY}-meta")

    if not categories or not name:
        st.stop()

    address = Address(actor.id, Workflow, categories=categories, name=name)
    context: DeployInitialState | None = st.session_state.get(f"{_KEY}-context")
    if data_store.occupied(address) and (
        context is None or context.address != str(address)
    ):
        st.error(f"Workflow {address} already exists")
        st.stop()

    cached = CachedWorkflowManager(data_store)
    version = select_workflow(cached)
    if version is None:
        return

    if st.button("Deploy upstream", key=f"{_KEY}-deploy"):
        _deploy_upstream(access, actor, address, cached, version)

    context = st.session_state.get(f"{_KEY}-context")
    if not context:
        st.info("Select a repository and version, then deploy to start curation.")
        return

    workflow_editor(_KEY, init_state=context, desc=desc, data_store=data_store)
