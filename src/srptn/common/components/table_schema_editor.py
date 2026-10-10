"""Editor for one curated workflow table (example + row schema).

The curation flow keeps the row schema authoritative and edited by hand, so the
column controls only rebuild the example; the schema ACE is left untouched
across structural edits.  Returns the updated :class:`TableSpec` for the caller
to persist.
"""

from __future__ import annotations

from typing import Sequence

import polars as pl
import streamlit as st
import yaml
from streamlit_ace import st_ace

from ..utils.workflow_tables import TableSpec, infer_table_schema, schema_columns
from ..utils.yaml_utils import parse_yaml
from .table_editor import column_controls, editable_table

_TABLE_ACE_HEIGHT = 220


def table_schema_editor(
    key: str,
    identifier: str,
    spec: TableSpec,
    paths: Sequence[str],
):
    """Render one table's example/schema editors and return the current spec."""
    row_schema = spec.schema
    example = spec.example
    prefix = f"{key}-{identifier}"
    revision = st.session_state.get(f"{prefix}-revision", 0)

    col1, col2 = st.columns(2)
    fields_label = ", ".join(".".join(map(str, field)) for field in spec.fields)
    st.caption(f"{identifier}: {fields_label} -> {list(paths)}")
    with col1:
        if not paths:
            st.warning("No file path declared for this table.")
        if not example:
            columns = schema_columns(row_schema) or ["column"]
            example = dict.fromkeys(columns, [])
        frame, change = column_controls(prefix, pl.DataFrame(example))
        if change:
            example = frame.to_dict(as_series=False)
            spec = TableSpec(spec.fields, row_schema, example)
            revision += 1
            st.session_state[f"{prefix}-revision"] = revision
        frame = pl.DataFrame(example)
        edited = editable_table(f"{prefix}-editor-{revision}", frame)
        new_example = edited.to_dict(as_series=False)
    with col2:
        default_schema = yaml.safe_dump(
            (row_schema if isinstance(row_schema, dict) else infer_table_schema(frame)),
            sort_keys=False,
        )
        new_schema_text = st_ace(
            default_schema,
            language="yaml",
            height=_TABLE_ACE_HEIGHT,
            auto_update=False,
            key=f"{prefix}-schema",
        )
        parsed, parse_error = parse_yaml(new_schema_text)
        new_schema = (
            parsed if not parse_error and isinstance(parsed, dict) else row_schema
        )

    if new_example != example or new_schema != row_schema:
        spec = TableSpec(fields=spec.fields, schema=new_schema, example=new_example)
    with col1:
        for message in spec.errors():
            st.error(f"table '{identifier}': {message}")
    return spec
