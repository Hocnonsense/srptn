import streamlit as st


from ..access.store import AccessStore
from ..accounts.policy import Actor
from ..data import Address
from ..data.entities.analysis import WorkflowManager
from ..data.entities.workflow import Workflow
from ..data.fs import FSDataStore
from ..utils.snakedeploy import CachedWorkflowManager, RepoRefs, Version
from ..utils.schema_inference import infer_schema, update_schema
from ..utils.workflow_tables import TableSpec, tables_from_data
from ..utils.yaml_utils import load_yaml
from .config_editor import ace_config_editor, create_form
from .table_schema_editor import table_schema_editor
from .ui_components import persistent_text_input

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

_DEFAULT_REPOSITORY = "https://github.com/snakemake-workflows/rna-seq-kallisto-sleuth"
_REPOSITORY_URL_LABEL = (
    f"Workflow repository URL (e.g. {_DEFAULT_REPOSITORY}, you can also explore from "
    "the [catalog](https://snakemake.github.io/snakemake-workflow-catalog/docs/all_standardized_workflows.html))"
)

_META_LABELS = {f"workflow-meta-{i.lower()}": i for i in ("Tag", "Branch", "Commit")}
_PICKER = "workflow-meta-picker"
_SIGNATURE = "workflow-meta-refs-signature"

_SELECTED_MANAGER = "workflow-selected-manager"
_SELECTED_VERSION = "workflow-selected-version"
_SELECTED_WORKFLOW = "workflow-selected-entity"


def workflow_selector(
    access: AccessStore,
    actor: Actor,
    address: Address,
    data_store: FSDataStore,
):
    """Pick a repository/version, deploy it on demand and return its manager."""
    cached = CachedWorkflowManager(data_store)
    version = select_workflow(cached)
    if version is None:
        return None
    if st.button("Deploy", key="workflow-meta-deploy"):
        return _deploy(cached, access, actor, address, version)
    if st.session_state.get(_SELECTED_VERSION) == version.selection(address):
        return st.session_state.get(_SELECTED_MANAGER)


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


def _select_repository(cached: CachedWorkflowManager):
    """Render the cached/external repository picker and return the chosen URL."""
    repositories = list(cached.available_workflows())
    pending = st.session_state.pop("workflow-meta-pending-source", None)
    if pending in repositories:
        st.session_state["workflow-meta-source"] = pending

    PROMPT_TEXT_INPUT = "Enter URL in text box"
    source = st.selectbox(
        "Select workflow repository",
        [*repositories, PROMPT_TEXT_INPUT],
        key="workflow-meta-source",
    )
    if source == PROMPT_TEXT_INPUT:
        url = persistent_text_input(
            _REPOSITORY_URL_LABEL, "workflow-meta-url", _DEFAULT_REPOSITORY
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
    return url


def _read_refs(cached: CachedWorkflowManager, url: str) -> RepoRefs | None:
    """Return the cached Git refs for ``url`` (None for a plain local directory)."""
    key = f"workflow-refs:{url}"
    if key not in st.session_state:
        st.session_state[key] = cached.read_workflow_refs(url)
    return st.session_state[key]


def select_workflow(cached: CachedWorkflowManager):
    """Render the repository and version controls and return the pending version."""
    url = _select_repository(cached)
    if url is None:
        return None
    try:
        refs = _read_refs(cached, url)
    except BaseException as error:
        st.error(f"Failed to read workflow versions: {error}")
        return None
    if refs is None:
        st.caption("Local workflow directory")
        return Version(url)
    if not refs.commits:
        st.info("This Git repository contains no commits.")
        return None
    return Version(url, *_version_picker(cached, url, refs))


def _reset_unless_current(url: str, refs: RepoRefs):
    """Seed default tag/branch/commit unless they already match these refs."""
    signature = (
        url,
        refs.head,
        tuple(refs.commits),
        tuple(refs.tags.items()),
        tuple(refs.branches.items()),
    )
    if st.session_state.get(_SIGNATURE) == signature and all(
        key in st.session_state for key in _META_LABELS
    ):
        return

    commit = refs.default_commit
    tag = next((name for name, sha in refs.tags.items() if sha == commit), None)
    branch = (
        next((name for name, sha in refs.branches.items() if sha == commit), None)
        if tag is None
        else None
    )
    st.session_state.update(zip(_META_LABELS, (tag, branch, commit)))
    st.session_state[_SIGNATURE] = signature


def _version_picker(cached: CachedWorkflowManager, url: str, refs: RepoRefs):
    """Render the tag/branch/commit row and its picker; return the chosen refs."""
    _reset_unless_current(url, refs)
    _render_version_row(cached, url, refs)
    _render_picker(refs)

    error = st.session_state.pop("workflow-meta-fetch-error", None)
    if error is not None:
        st.error(f"Failed to fetch workflow versions: {error}")
    return tuple(st.session_state[key] for key in _META_LABELS)


def _refresh_refs(cached: CachedWorkflowManager, url: str):
    try:
        st.session_state[f"workflow-refs:{url}"] = cached.read_workflow_refs(
            url, refresh=True
        )
        st.session_state[_PICKER] = None
    except BaseException as error:
        st.session_state["workflow-meta-fetch-error"] = str(error)


def _render_version_row(cached: CachedWorkflowManager, url: str, refs):
    """Render the Tag/Branch/Commit buttons and the refresh control."""
    tag, branch, commit = (st.session_state[key] for key in _META_LABELS)
    commit_label = _commit_label(refs, commit)
    fields = zip(_META_LABELS, (tag, branch, commit_label))
    with st.container(key="workflow-version-row"):
        columns = st.columns(
            [4 if tag is not None else 0.6, 4 if branch is not None else 0.6, 6, 1],
            vertical_alignment="center",
        )
        for index, (key, value) in enumerate(fields):
            with columns[index]:
                st.button(
                    f"{value} ▾" if value is not None else "▾",
                    key=f"{key}-open",
                    help=_META_LABELS[key],
                    use_container_width=True,
                    on_click=_toggle_picker,
                    args=(key,),
                )
        with columns[3]:
            st.button(
                "↻",
                key="workflow-meta-fetch",
                on_click=_refresh_refs,
                args=(cached, url),
            )


def _render_picker(refs: RepoRefs):
    """Render the native selectbox for the currently open ref kind."""
    picker = st.session_state.get(_PICKER)
    if picker not in _META_LABELS:
        return

    label = _META_LABELS[picker]
    names = {"Tag": refs.tags, "Branch": refs.branches}.get(label)
    widget_key = f"{picker}-picker"
    st.session_state[widget_key] = None
    with st.container(key="workflow-version-picker"):
        st.selectbox(
            label,
            list(refs.commits) if names is None else list(names),
            index=None,
            key=widget_key,
            placeholder=f"Select a {label.lower()}",
            format_func=lambda value: _version_label(refs, value, names),
            on_change=_select_ref,
            args=(picker, names),
        )
    st.html(auto_open_script, unsafe_allow_javascript=True)


def _toggle_picker(key: str):
    current = st.session_state.get(_PICKER)
    st.session_state[_PICKER] = None if current == key else key


def _select_ref(picker: str, names: dict[str, str] | None):
    st.session_state[_PICKER] = None
    value = st.session_state[f"{picker}-picker"]
    if value is None:
        return
    if names is None:
        values = None, None, value
    else:
        values = (
            (value, None, names[value])
            if _META_LABELS[picker] == "Tag"
            else (None, value, names[value])
        )
    st.session_state.update(zip(_META_LABELS, values))


def _commit_label(refs: RepoRefs, commit: str):
    _, date = refs.commits[commit]
    return f"{commit[:12]} · {date:%Y-%m-%d %H:%M UTC}"


def _version_label(refs: RepoRefs, value: str, names: dict | None) -> str:
    """Format a commit (``names`` is None) or a named tag/branch reference."""
    if names is None:
        subject, date = refs.commits[value]
        return f"{value[:12]} · {date:%Y-%m-%d %H:%M UTC} · {subject}"
    subject, date = refs.commits[names[value]]
    return f"{value} · {subject} · {date:%Y-%m-%d %H:%M UTC}"


def _deploy(
    cached: CachedWorkflowManager,
    access: AccessStore,
    actor: Actor,
    address: Address,
    version: Version,
):
    """Resolve the commit and deploy a workspace for editing before Store."""
    selection = version.selection(address)
    if st.session_state.get(_SELECTED_VERSION) == selection:
        return st.session_state[_SELECTED_MANAGER]

    for key in list(st.session_state):
        if isinstance(key, str) and key.startswith("workflow-config-"):
            del st.session_state[key]
    workspace = access.workspace(actor, address)
    manager = WorkflowManager.deploy(workspace, version, cached)
    if manager is not None:
        st.session_state[_SELECTED_MANAGER] = manager
        st.session_state[_SELECTED_VERSION] = selection
    return manager


def workflow_editor(workflow: Workflow):
    """Edit a curated workflow's runner-facing config and declared tables.

    The ``Workflow`` contract is authoritative: config/schema come from the
    entity (never the deployed repository), the config never loads workspace
    files, and the declared tables are edited in memory and written only at
    store time.

    :returns: ``(config, tables)`` -- the edited config mapping and the
        ``{identifier: TableSpec}`` mapping.
    """
    config_viewer = st.radio(
        "Configuration editor mode",
        ["Form", "Text Editor"],
        horizontal=True,
    )

    st.divider()
    if st.session_state.get("workflow-config-form") is None:
        config = load_yaml(workflow.config) or {}
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
    tables = st.session_state[tables_key]
    return config, _declared_tables(key, config, tables)


def _declared_tables(key: str, config, tables: dict[str, TableSpec]):
    """Render each declared table path as its own in-memory editor.

    Config fields that resolve to the same file share one example; every
    distinct file path is edited (and later written) separately, so the result
    is keyed by path.  A path may only carry one row schema: two declarations
    that disagree are a contract error and are refused rather than silently
    overwritten (one file cannot hold two schemas).  The row schema stays
    read-only -- it is part of the curated contract, not runner input.
    """
    by_path: dict[str, TableSpec] = {}
    for spec in tables.values():
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
    if not by_path:
        return {}
    st.markdown("**Declared tables** — editable example (left) vs row schema (right)")
    for path, spec in by_path.items():
        by_path[path] = table_schema_editor(
            key, path, spec, [path], read_only_schema=True
        )
    return by_path
