"""Compose a reproducible figure from a table in a readable Analysis."""

import streamlit as st

from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor
from srptn.common.components.figure_editor import figure_editor
from srptn.common.data.entities.analysis import Analysis
from srptn.common.data.fs import fs_data_store
from srptn.common.extensions.source import (
    PREVIEW_ROWS,
    read_table_preview,
    vega_schema,
)
from srptn.common.utils.table_utils import table_suffix
from srptn.views import PageInfo


@PageInfo.wrap("Figure Extension")
def page_figure_edit(actor: Actor):
    st.title("Compose figure")
    st.markdown(
        "Choose an Analysis, then a table produced in its workspace, "
        "map the chart encodings and inspect a bounded preview of that table."
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

    frame = read_table_preview(workspace, selected_table, limit=PREVIEW_ROWS)
    if frame is None:
        st.error(f"Failed to read table {selected_table}.")
        return

    schema, skipped = vega_schema(frame.schema)
    if skipped:
        st.warning(
            "These columns are not supported by the first chart slice and are "
            f"hidden: {', '.join(skipped)}."
        )
    if not schema:
        st.error("The selected table has no usable columns.")
        return
    if frame.height == PREVIEW_ROWS:
        preview_desc = (
            f"Preview table: top {PREVIEW_ROWS} rows. "
            "The full table is not read by the browser."
        )
    else:
        preview_desc = f"Preview table: {frame.height} rows."
    with st.expander(preview_desc):
        st.dataframe(frame, width="stretch", height=500, hide_index=True)

    binding = {
        "analysis_id": str(analysis.address),
        "logical_path": selected_table,
        "schema": schema,
    }
    figure_editor(
        "figure-extension",
        schema,
        frame=frame,
        input_binding=binding,
    )
