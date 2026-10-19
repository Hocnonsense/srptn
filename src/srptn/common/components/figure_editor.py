"""Click-to-edit form for a reproducible Vega-Lite definition.

The caller supplies an authorized column schema and, for preview, an already
sampled table.  The component never chooses a host path or executes a generated
rule; it builds the declarative definition and renders the sample through
Vega-Lite in the browser.
"""

from __future__ import annotations

import json

from typing import Mapping

import polars as pl
import streamlit as st

from ..extensions.source import preview_records
from ..extensions.vega import (
    AGGREGATES,
    CHART_TYPES,
    FILTER_OPS,
    FigureConfig,
    Filter,
    definition,
)

_NO_COLOR = "(none)"
_NO_SIZE = "(none)"


def figure_editor(
    key: str,
    columns: Mapping[str, str],
    *,
    frame: pl.DataFrame,
    input_binding: Mapping | None = None,
):
    """Render the editor and return ``(config, definition, issues)``.

    ``columns`` maps column names to Vega-Lite types.  When ``frame`` is given,
    it is treated as a bounded sample and rendered after the definition
    validates; the exported spec keeps the named ``data`` source for the
    formal renderer.  ``input_binding`` records the selected table.
    """
    all_columns = list(columns)
    quantitative = [
        column for column, vega_type in columns.items() if vega_type == "quantitative"
    ]
    numericish = [
        column
        for column, vega_type in columns.items()
        if vega_type in ("quantitative", "temporal")
    ]
    size_columns = [
        column
        for column, vega_type in columns.items()
        if vega_type in ("quantitative", "ordinal", "nominal")
    ]
    if not all_columns:
        st.error("The schema provides no columns.")
        return None, None, []

    def label(column: str):
        return f"{column} ({columns[column]})"

    chart = st.selectbox(
        "Chart type",
        CHART_TYPES,
        format_func=str.capitalize,
        key=f"{key}-chart",
        help="The first vertical slice supports point, bar and line marks.",
    )
    x = st.selectbox(
        "X field",
        all_columns,
        format_func=label,
        key=f"{key}-x",
        help="Any column can be used as the horizontal axis.",
    )

    aggregate_options = [
        item for item in AGGREGATES if chart != "line" or item != "count"
    ]
    aggregate = st.selectbox(
        "Y aggregation",
        aggregate_options,
        key=f"{key}-aggregate-{chart}",
        help="Use COUNT for a bar chart of row counts; otherwise aggregate the y field.",
    )

    y_options = quantitative if chart == "bar" or aggregate != "none" else numericish
    if not y_options and aggregate != "count":
        st.error("The schema has no suitable y column for this chart.")
        return None, None, []
    y = st.selectbox(
        "Y field",
        y_options,
        format_func=label,
        key=f"{key}-y-{chart}-{aggregate}",
        disabled=aggregate == "count",
        help="Bar and aggregated charts require a quantitative y column.",
    )

    color = st.selectbox(
        "Color (optional)",
        [_NO_COLOR, *all_columns],
        format_func=lambda item: label(item) if item != _NO_COLOR else "No color",
        key=f"{key}-color",
    )
    size = st.selectbox(
        "Size (optional)",
        [_NO_SIZE, *size_columns],
        format_func=lambda item: label(item) if item != _NO_SIZE else "No size",
        key=f"{key}-size",
    )

    st.markdown("**Labels**")
    title = st.text_input("Chart title", key=f"{key}-title")
    c1, c2 = st.columns(2)
    with c1:
        x_title = st.text_input("X axis label", key=f"{key}-x-title")
    with c2:
        y_title = st.text_input("Y axis label", key=f"{key}-y-title")

    with st.expander("Filters (optional)"):
        st.caption(
            "Filters apply before encoding. Use comma-separated values for IN; "
            "comparison operators require a quantitative column."
        )
        filters = _filter_rows(key, all_columns)

    config = FigureConfig(
        chart=chart,
        x=x,
        y=None if aggregate == "count" else y,
        color=None if color == _NO_COLOR else color,
        size=None if size == _NO_SIZE else size,
        aggregate=aggregate,
        filters=filters,
        title=title,
        x_title=x_title,
        y_title=y_title,
    )
    payload, issues = definition(config, columns, input_binding=input_binding)

    if issues:
        st.markdown("**Preview**")
        st.error("The chart definition is not valid yet.")
        for issue in issues:
            st.error(str(issue))
    elif payload is not None:
        if frame is not None:
            st.markdown("**Preview**")
            if frame.height == 0:
                st.info("The sampled table has no rows.")
            else:
                preview = dict(payload["spec"])
                preview["data"] = {"values": preview_records(frame)}
                st.vega_lite_chart(
                    preview,
                    width="stretch",
                    key=f"{key}-preview",
                )

        st.markdown("**Definition**")
        st.success("Valid Vega-Lite definition.")
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        st.code(text, language="json")
        st.download_button(
            "Download definition (JSON)",
            data=text,
            file_name="figure-extension.json",
            mime="application/json",
            key=f"{key}-download",
            width="stretch",
        )
    return config, payload, issues


def _filter_rows(key: str, columns: list[str]):
    frame = pl.DataFrame(
        schema={"column": pl.String, "op": pl.String, "value": pl.String}
    )
    edited = st.data_editor(
        frame.to_pandas(),
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"{key}-filters",
        column_config={
            "column": st.column_config.SelectboxColumn("Column", options=columns),
            "op": st.column_config.SelectboxColumn(
                "Operator", options=list(FILTER_OPS)
            ),
            "value": st.column_config.TextColumn("Value"),
        },
    )
    rows = pl.from_pandas(edited).to_dicts() if not edited.empty else []
    return tuple(
        Filter(
            column=str(row["column"]),
            op=str(row["op"]),
            value=str(row.get("value") or ""),
        )
        for row in rows
        if row.get("column") and row.get("op")
    )
