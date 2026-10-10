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
    prefix = f"{key}-{identifier}"
    data_key = f"{prefix}-data"
    if data_key not in st.session_state:
        columns = list(spec.example) or schema_columns(row_schema) or ["column"]
        st.session_state[data_key] = pl.DataFrame(
            spec.example or dict.fromkeys(columns, [])
        )

    col1, col2 = st.columns(2)
    fields_label = ", ".join(".".join(map(str, field)) for field in spec.fields)
    st.caption(f"{identifier}: {fields_label} -> {list(paths)}")
    with col1:
        if not paths:
            st.warning("No file path declared for this table.")
        change = column_controls(prefix)
        frame = editable_table(prefix, reset=bool(change))
        example = frame.to_dict(as_series=False)
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

    spec = TableSpec(spec.fields, new_schema, example)
    with col1:
        for message in spec.errors():
            st.error(f"table '{identifier}': {message}")
    return spec
