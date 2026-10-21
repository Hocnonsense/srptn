"""Compose a reproducible figure from a table in a readable Analysis."""

import streamlit as st

from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor
from srptn.common.components.figure_editor_component import figure_editor_component
from srptn.common.data.entities.analysis import Analysis
from srptn.common.data.fs import fs_data_store
from srptn.common.extensions.source import (
    preview_records,
    read_table_full,
    vega_schema,
)
from srptn.common.utils.table_utils import table_suffix
from srptn.views import PageInfo


@PageInfo.wrap("Figure Extension")
def page_figure_edit(actor: Actor):
    st.title("Compose figure")
    st.markdown(
        "Choose an Analysis and a table, then build the figure in the embedded "
        "Vega-Lite editor. The editor runs in the browser; only the declarative "
        "spec comes back to SRPTN."
    )

    access = AccessStore(fs_data_store())
    analyses = access.entities(actor, Analysis)
    if not analyses:
        st.warning("No readable analysis found.")
        return

    analysis_names = [str(item.address) for item in analyses]
    selected = st.selectbox(
        "Analysis",
        analysis_names,
        key="figure-extension-analysis",
    )
    analysis = next(item for item in analyses if str(item.address) == selected)
    workspace = access.workspace(actor, analysis.address)
    tables = list(
        dict.fromkeys(path for path in analysis.workflow_files() if table_suffix(path))
    )
    if not tables:
        st.warning("This analysis has no table in its DAG outputs or stored files.")
        return
    selected_table = st.selectbox("Table", tables, key="figure-extension-table")

    frame = read_table_full(workspace, selected_table)
    if frame is None:
        st.error(f"Failed to read table {selected_table}.")
        return

    schema, skipped = vega_schema(frame.schema)
    if skipped:
        st.warning(
            "These columns are not supported by the first chart slice and are "
            f"ignored by the editor: {', '.join(skipped)}."
        )
    if not schema:
        st.error("The selected table has no usable columns.")
        return

    rows = preview_records(frame)
    if len(rows) > 10_000:
        st.warning(
            "This prototype sends the selected table into the browser component. "
            "Large tables may be slow; the host data endpoint is still pending."
        )
    component_key = f"figure-editor:{analysis.address}:{selected_table}:{len(rows)}"
    value = figure_editor_component(
        rows=rows,
        schema=schema,
        key=component_key,
    )
    if value:
        if value["issues"]:
            st.warning("The current figure definition has validation issues.")
            for issue in value["issues"]:
                st.write(issue)
        if value["spec"]:
            st.caption("The embedded editor returned a declarative Vega-Lite spec.")
            with st.expander("Current definition JSON", expanded=False):
                st.json(value["spec"])
