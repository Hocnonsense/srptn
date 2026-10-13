"""Streamlit editor that builds a :class:`TableConvert` from long-table inputs.

``_table_convert_editor`` is the Dataset-metadata editor: it records operations
step by step and returns ``(table, rules)`` early when the next step is
undefined.  ``sample_table_editor`` wraps it, renders the overlay side table and
previews the result from the returned table (corrected against the schema and
joined with the overlay).  Neither touches the filesystem.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import polars as pl
import streamlit as st


from ..components.sample_sheet import FILE_COLUMN
from ..transform.convert import TableConvert, merge_overlay
from ..transform.models import Condition, TransformRules
from ..utils.table_schema import coerce_frame, table_errors
from .table_editor import column_controls, editable_table


def sample_table_editor(
    key: str, tables: dict[str, pl.DataFrame] | None, schema: Mapping
):
    """Build one declared table: Dataset metadata plus an overlay side table.

    The preview is always rendered; every problem (build, overlay and schema
    validation) is listed below it.
    """
    ret = _table_convert_editor(key, tables)
    st.markdown("**5. Overlay side table** (optional; join keys + extra columns)")
    overlay = _render_overlay(key, ret)

    errors = []
    if ret:
        table, rules = ret
        final = merge_overlay(table, overlay, rules.renamed_index, errors)
    elif overlay is not None:
        rules = None
        final = overlay
    else:
        rules = final = None

    st.markdown("**Preview**")
    if final is None:
        st.info("Select input tables (or fill the overlay) to see a preview.")
        return None
    final, _ = coerce_frame(final, schema, errors)
    _display(final, key)
    # only validate the schema once the table built cleanly
    for issue in errors or table_errors(final, schema):
        st.error(issue)
    return TableConvert(schema, rules, overlay)


def _display(frame: pl.DataFrame, key: str):
    """Render the preview, joining list cells into space-separated text."""
    lists = [
        column for column in frame.columns if frame.schema[column] == pl.List(pl.String)
    ]
    if lists:
        frame = frame.with_columns(
            [pl.col(column).list.join(" ").alias(column) for column in lists]
        )
    st.dataframe(frame, use_container_width=True, hide_index=True, key=f"{key}-preview")


def _select_common(
    key: str, tables: dict[str, pl.DataFrame]
) -> tuple[list[str], list[str]]:
    """Pick tables; return ``(sources, frames, common_columns)`` or ``(None, [], [])``."""
    names = list(tables)
    selected = st.multiselect("Tables", names, default=names[:1], key=f"{key}-tables")
    if not selected:
        return [], []
    common = list(tables[selected[0]].columns)
    for name in selected[1:]:
        new = set(tables[name].columns)
        common = [column for column in common if column in new]
    return selected, common


def _table_convert_editor(
    key: str,
    tables: dict[str, pl.DataFrame] | None,
):
    """Build the Dataset-metadata table step by step.

    Returns ``(table, operations)`` where ``table`` is the fully processed
    result so far and ``operations`` (``TransformRules.sources``/``columns`` +
    group/output) record how to reproduce it from the source tables.
    """
    if not tables:
        return
    st.markdown("**1. Input tables**")
    sources, common = _select_common(key, tables)
    if not sources:
        return
    if common[0] != FILE_COLUMN:
        st.warning(f"The selected tables have no shared '{FILE_COLUMN}' column.")
        return

    index_columns = st.multiselect(
        "Index columns", common[1:], default=common[1:], key=f"{key}-index"
    )
    if not index_columns:
        st.info("Choose at least one index column.")
        return
    columns = list(dict.fromkeys([FILE_COLUMN, *index_columns]))
    trans = TransformRules(
        sources=tuple(sources), columns=tuple(columns), pivot_values=(FILE_COLUMN,)
    )
    inputs = trans.merge(tables)

    st.markdown("**2. Filter files**")
    trans.conditions = _filter_rows(key, inputs)
    try:
        inputs = trans.filter(inputs)
    except ValueError as error:
        st.error(f"Filter error: {error}")
        return

    st.markdown("**3. Pivot columns** (empty keeps the long table)")
    pivot_columns = st.multiselect(
        "Pivot columns",
        [column for column in index_columns if column != FILE_COLUMN],
        key=f"{key}-column",
    )
    if not pivot_columns:
        return inputs, trans

    trans.pivot_columns = tuple(pivot_columns)
    pivot = trans.pivot(inputs)

    row_keys = trans.pivot_indexes
    pivoted_columns = [column for column in pivot.columns if column not in row_keys]
    st.markdown("**4. Output columns** (rename / keep value as list)")
    trans.renames = _select_rename(key, row_keys, pivoted_columns)
    return trans.renamed(pivot), trans


def _filter_rows(key: str, inputs: pl.DataFrame):
    condition_rows = _edit_rows(
        f"{key}-conditions",
        {
            "column": pl.String,
            "op": pl.String,
            "value": pl.String,
            "negate": pl.Boolean,
        },
        [],
        {
            "column": st.column_config.SelectboxColumn(
                "Column", options=inputs.columns
            ),
            "op": st.column_config.SelectboxColumn(
                "Operator", options=Condition.SUPPORTED_OPS.keys()
            ),
            "value": st.column_config.TextColumn("Value"),
            "negate": st.column_config.CheckboxColumn("Not"),
        },
    )
    return tuple(
        Condition(
            str(row["column"]),
            str(row["op"]),
            row.get("value"),
            negate=bool(row.get("negate")),
        )
        for row in condition_rows
        if row.get("column") and row.get("op")
    )


def _select_rename(key, indexes: list[str], columns: list[str]):
    options = indexes + columns
    condition_rows = _edit_rows(
        f"{key}-renames",
        {"column": pl.String, "rename": pl.String},
        [{"column": column, "rename": ""} for column in options],
        {
            "column": st.column_config.SelectboxColumn("Column", options=options),
            "rename": st.column_config.TextColumn("Rename"),
        },
    )
    mapped: dict[str, str] = {}
    for row in condition_rows:
        column = row.get("column")
        if column:
            if str(column) in mapped:
                st.warning(
                    f"Column '{column}' is already renamed to '{mapped[str(column)]}'."
                )
            mapped[str(column)] = str(row.get("rename") or column)
    return mapped


def _render_overlay(key: str, ret: tuple[pl.DataFrame, TransformRules] | None):
    okey = f"{key}-overlay"
    signature = ret[1].renamed_index if ret is not None else ()
    reset = st.session_state.get(f"{okey}-signature") != signature
    if reset:
        # One row per output row key; user adds the extra columns.
        if ret is None:
            init = pl.DataFrame({})
        else:
            init = ret[0].select(signature)
            if not ret[1].pivot_columns:
                init = init.unique()
            # else already unique after a pivot
        st.session_state[f"{okey}-data"] = init
        st.session_state[f"{okey}-signature"] = signature
    if signature:
        st.caption("Index columns: " + (", ".join(signature)))
    overlay = editable_table(okey, reset=reset or bool(column_controls(okey)))
    if overlay.height:
        return overlay


def _edit_rows(
    key: str,
    schema: Mapping[str, type[pl.DataType]],
    default_rows: Sequence[Mapping],
    column_config: Mapping,
):
    frame = pl.DataFrame(list(default_rows), schema=schema)
    edited = st.data_editor(
        frame.to_pandas(),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"{key}-editor",
        column_config=column_config,
    )
    return pl.from_pandas(edited).to_dicts()
