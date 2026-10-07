import streamlit as st
import subprocess
from snakedeploy.exceptions import UserError

from ..utils.snakedeploy import CachedWorkflowManager
from .config_editor import ace_config_editor, config_editor
from .schemas import infer_schema, update_schema
from .ui_components import persistent_text_input
from ..data import Address
from ..data.fs import FSDataStore
from ..data.entities.analysis import WorkflowManager

auto_open_script = """
<script>(() => {
    let observer;
    let timer;
    let expanded = false;
    const expand = () => {
        if (expanded) return;
        const input = document.querySelector(
            '.st-key-workflow-version-picker input[role="combobox"]'
        );
        if (!input || input.closest('[data-stale="true"]')) return;
        expanded = true;
        observer.disconnect();
        clearTimeout(timer);
        input.focus();
        if (input.getAttribute('aria-expanded') !== 'true') {
            input.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'ArrowDown', code: 'ArrowDown', keyCode: 40,
                which: 40, bubbles: true,
            }));
        }
    };
    observer = new MutationObserver(() => requestAnimationFrame(expand));
    observer.observe(document.body, {
        childList: true, subtree: true, attributes: true,
    });
    timer = setTimeout(() => observer.disconnect(), 5000);
    requestAnimationFrame(expand);
})();
</script>
"""


def workflow_selector(address: Address, data_store: FSDataStore):
    """Select a cached or fetched repository and Git refs and confirmed commit hashes."""
    cached = CachedWorkflowManager(data_store)
    selected = _select_workflow(cached)
    if selected is None:
        return None
    url, tag, branch, commit = selected
    selection = (url, commit, str(address))
    if st.button("Deploy", key="workflow-meta-deploy"):
        return _selected_workflow(cached, address, data_store, url, tag, branch, commit)
    if st.session_state.get("workflow-selected-version") == selection:
        return st.session_state.get("workflow-selected-manager")


def _select_workflow(cached: CachedWorkflowManager):
    repositories = list(cached.available_workflows())
    pending_source = st.session_state.pop("workflow-meta-pending-source", None)
    if pending_source in repositories:
        st.session_state["workflow-meta-source"] = pending_source
    external = "Enter URL in text box"
    source = st.selectbox(
        "Select workflow repository",
        [*repositories, external],
        key="workflow-meta-source",
    )
    if source == external:
        url = persistent_text_input(
            "Workflow repository URL (e.g. https://github.com/snakemake-workflows/rna-seq-kallisto-sleuth, "
            "you can also explore from "
            "the [catalog](https://snakemake.github.io/snakemake-workflow-catalog/docs/all_standardized_workflows.html))",
            "workflow-meta-url",
            "https://github.com/snakemake-workflows/rna-seq-kallisto-sleuth",
        ).strip()
        if url and url not in repositories:
            cached.read_workflow_refs(url)
            if url in cached.available_workflows():
                st.session_state["workflow-meta-pending-source"] = url
                st.rerun()
    else:
        url = source
    if not url:
        st.info("Select a cached workflow or enter a repository URL.")
        return None

    refs_key = f"workflow-refs:{url}"
    try:
        if refs_key not in st.session_state:
            refs = st.session_state[refs_key] = cached.read_workflow_refs(url)
        else:
            refs = st.session_state[refs_key]
    except BaseException as error:
        st.error(f"Failed to read workflow versions: {error}")
        return None
    tag_key, branch_key, commit_key = [
        f"workflow-meta-{i}" for i in ("tag", "branch", "commit")
    ]
    if refs is None:
        tag = branch = commit = None
        st.caption("Local workflow directory")
    else:
        if not refs.commits:
            st.info("This Git repository contains no commits.")
            return None
        signature = (
            url,
            refs.head,
            tuple(refs.commits),
            tuple(refs.tags.items()),
            tuple(refs.branches.items()),
        )
        if st.session_state.get("workflow-meta-refs-signature") != signature or any(
            key not in st.session_state for key in (tag_key, branch_key, commit_key)
        ):
            commit = refs.default_commit
            tag = next((name for name, sha in refs.tags.items() if sha == commit), None)
            branch = (
                next(
                    (name for name, sha in refs.branches.items() if sha == commit), None
                )
                if tag is None
                else None
            )
            st.session_state.update(
                {
                    tag_key: tag,
                    branch_key: branch,
                    commit_key: commit,
                    "workflow-meta-refs-signature": signature,
                }
            )

        picker_key = "workflow-meta-picker"

        def toggle_picker(key):
            st.session_state[picker_key] = (
                None if st.session_state.get(picker_key) == key else key
            )

        def select_version(key, values):
            value = st.session_state[f"{key}-picker"]
            if key == commit_key:
                st.session_state[commit_key] = value
                st.session_state[tag_key] = None
                st.session_state[branch_key] = None
            else:
                st.session_state[key] = value
                if value is not None:
                    st.session_state[commit_key] = values[value]
                    other = branch_key if key == tag_key else tag_key
                    st.session_state[other] = None
            st.session_state[picker_key] = None

        def refresh_refs():
            try:
                st.session_state[refs_key] = cached.read_workflow_refs(
                    url, refresh=True
                )
                st.session_state[picker_key] = None
            except BaseException as error:
                st.session_state["workflow-meta-fetch-error"] = str(error)

        def version_label(sha, name=None):
            subject, date = refs.commits[sha]
            date_str = f"{date:%Y-%m-%d %H:%M UTC}"
            if name is None:
                return f"{sha[:12]} · {date_str} · {subject}"
            return f"{name} · {subject} · {date_str}"

        tag, branch, commit = (
            st.session_state[key] for key in (tag_key, branch_key, commit_key)
        )
        with st.container(key="workflow-version-row"):
            columns = st.columns(
                [
                    4 if tag is not None else 0.6,
                    4 if branch is not None else 0.6,
                    6,
                    1,
                ],
                vertical_alignment="center",
            )
            for column, label, key, value in (
                (columns[0], "Tag", tag_key, tag),
                (columns[1], "Branch", branch_key, branch),
                (
                    columns[2],
                    "Commit",
                    commit_key,
                    f"{commit[:12]} · {refs.commits[commit][1]:%Y-%m-%d %H:%M UTC}",
                ),
            ):
                with column:
                    st.button(
                        f"{value} ▾" if value is not None else "▾",
                        key=f"{key}-open",
                        help=label,
                        use_container_width=True,
                        on_click=toggle_picker,
                        args=(key,),
                    )
            with columns[3]:
                st.button("↻", key="workflow-meta-fetch", on_click=refresh_refs)

        picker = st.session_state.get(picker_key)
        if picker in (tag_key, branch_key, commit_key):
            label = {tag_key: "Tag", branch_key: "Branch", commit_key: "Commit"}[picker]
            values = {tag_key: refs.tags, branch_key: refs.branches}.get(picker)
            widget_key = f"{picker}-picker"
            st.session_state[widget_key] = None
            with st.container(key="workflow-version-picker"):
                st.selectbox(
                    label,
                    list(refs.commits) if values is None else list(values),
                    index=None,
                    key=widget_key,
                    placeholder=f"Select a {label.lower()}",
                    format_func=lambda value: (
                        version_label(value)
                        if values is None
                        else version_label(values[value], value)
                    ),
                    on_change=select_version,
                    args=(picker, values),
                )
            st.html(auto_open_script, unsafe_allow_javascript=True)
        fetch_error = st.session_state.pop("workflow-meta-fetch-error", None)
        if fetch_error is not None:
            st.error(f"Failed to fetch workflow versions: {fetch_error}")
        tag, branch, commit = (
            st.session_state[key] for key in (tag_key, branch_key, commit_key)
        )
    return url, tag, branch, commit


def _selected_workflow(
    cached: CachedWorkflowManager,
    address: Address,
    data_store: FSDataStore,
    url: str,
    tag,
    branch,
    commit: str | None,
):
    if commit is None and (tag is not None or branch is not None):
        try:
            commit = cached.resolve_ref(url, tag=tag, branch=branch)
        except (OSError, subprocess.CalledProcessError, UserError, ValueError) as error:
            st.error(f"Failed to resolve workflow version: {error}")
            return None
    selection = (url, commit, str(address))
    if st.session_state.get("workflow-selected-version") != selection:
        for key in list(st.session_state):
            if isinstance(key, str) and key.startswith("workflow-config-"):
                del st.session_state[key]
        workspace = data_store.workspace(address)
        try:
            with workspace as data_path:
                cached.deploy(data_path, address.name, url, commit=commit)
            manager = WorkflowManager(url, tag, branch, workspace, commit=commit)
            manager.check()
            manager.export_metadata()
        except (
            OSError,
            subprocess.CalledProcessError,
            UserError,
            ValueError,
            RuntimeError,
        ) as error:
            workspace.clean()
            st.error(f"Failed to deploy workflow: {error}")
            return None
        except BaseException:
            workspace.clean()
            raise
        st.session_state["workflow-selected-manager"] = manager
        st.session_state["workflow-selected-version"] = selection
    return st.session_state["workflow-selected-manager"]


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
