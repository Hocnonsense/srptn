import streamlit as st
import yaml

from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor, Role
from srptn.common.components.entities import data_selector
from srptn.common.components.forms import entity_meta_editor
from srptn.common.components.schemas import infer_schema
from srptn.common.components.workflow_editor import (
    DeployInitialState,
    workflow_editor,
)
from srptn.common.components.workflows import select_workflow
from srptn.common.data import Address
from srptn.common.data.entities.analysis import WorkflowManager
from srptn.common.data.entities.workflow import Workflow
from srptn.common.data.fs import fs_data_store
from srptn.common.utils.snakedeploy import CachedWorkflowManager, Version
from srptn.common.utils.workflow_curation import load_yaml
from srptn.common.utils.yaml_utils import CustomSafeDumper
from srptn.views import PageInfo

_KEY = "workflow-new"


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
        internal_schema=schema_text,
    )
    st.session_state[f"{_KEY}-run"] = st.session_state.get(f"{_KEY}-run", 0) + 1


@PageInfo.wrap("New Workflow", Role.PUBLISHER)
def page_new_workflow(actor: Actor):
    """Curate and publish a Workflow entity from a pinned upstream repository."""
    data_store = fs_data_store()
    access = AccessStore(data_store)

    st.header("New Workflow", divider=True)
    categories, name, desc = entity_meta_editor(_KEY, "Workflow name")

    if not categories or not name:
        st.stop()

    address = Address(actor.id, Workflow, categories=categories, name=name)
    context: DeployInitialState | None = st.session_state.get(f"{_KEY}-context")
    if data_store.occupied(address) and (context is None or context.address != address):
        st.error(f"Workflow {address} already exists")
        st.stop()

    data_selector(access, actor, f"{_KEY}-datasets")

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
