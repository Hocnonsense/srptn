import streamlit as st

from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor, Role
from srptn.common.components.forms import entity_meta_editor
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
from srptn.views import PageInfo

_KEY = "workflow-new"
_CONTEXTS = f"{_KEY}-contexts"


def _contexts() -> dict[str, DeployInitialState]:
    return st.session_state.setdefault(_CONTEXTS, {})


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

    _contexts()[str(address)] = _get_init_state(manager)
    run_key = f"{_KEY}-{address}-run"
    st.session_state[run_key] = st.session_state.get(run_key, 0) + 1


def _reopen_deployed(access: AccessStore, actor: Actor, address: Address):
    """Rebuild the curation state from an unsaved deployment in the workspace.

    Returns ``None`` when there is nothing to reopen (no deployment) or when the
    address already holds a stored ``Workflow`` entity (``desc.md`` present).
    """
    workspace = access.workspace(actor, address)
    if workspace.desc_path.exists():
        return None
    if not (workspace.meta_path / "details.yml").exists():
        return None

    return _get_init_state(WorkflowManager.load(workspace))


def _get_init_state(manager: WorkflowManager):
    assert manager.config_path
    return DeployInitialState.from_workflow(
        manager.workspace.address,
        manager.version,
        manager.config_path,
        manager.get_schema("config"),
        manager.workspace.data_path,
    )


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
    context = _contexts().get(str(address))
    if context is None and data_store.occupied(address):
        # Reopen a deployment that was not stored yet instead of rejecting it,
        # so losing the session context (e.g. a page reload) is not fatal.
        context = _reopen_deployed(access, actor, address)
        if context is None:
            st.error(f"Workflow {address} already exists")
            st.stop()
        _contexts()[str(address)] = context

    cached = CachedWorkflowManager(data_store)
    version = select_workflow(cached)
    if version is None:
        return

    if st.button("Deploy", key=f"{_KEY}-deploy"):
        _deploy_upstream(access, actor, address, cached, version)

    context = _contexts().get(str(address))
    if not context:
        st.info("Select a repository and version, then deploy to start curation.")
        return

    workflow = workflow_editor(
        f"{_KEY}-{address}", init_state=context, desc=desc, data_store=data_store
    )
    if st.button(
        "Save workflow", key=f"{_KEY}-save-workflow", disabled=workflow is None
    ):
        assert workflow is not None
        workflow.store(data_store)
        st.success(f"Saved workflow {workflow.address}")
