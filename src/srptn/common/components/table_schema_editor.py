"""Editor for one curated workflow table (example + row schema).

The curation flow keeps the row schema authoritative and edited by hand, so the
column controls only rebuild the example; the schema ACE is left untouched
across structural edits.  The working frame is cast to the schema's declared
column types, so the example carries matching types and validation stays
strict.  Returns the updated :class:`TableSpec` for the caller to persist.
"""

from __future__ import annotations

from typing import Sequence

import streamlit as st
import yaml
from streamlit_ace import st_ace

from ..utils.schema_validation import schema_errors
from ..utils.workflow_tables import (
    TableSpec,
    coerce_frame,
    column_dtypes,
    infer_table_schema,
    nullify,
)
from ..utils.yaml_utils import parse_yaml
from .table_editor import column_controls, editable_table

_TABLE_ACE_HEIGHT = 220


def table_schema_editor(
    key: str,
    identifier: str,
    spec: TableSpec,
    paths: Sequence[str],
    *,
    read_only_schema: bool = False,
):
    """Render one table's example/schema editors and return the current spec.

    The schema (right) is authoritative and read first; the example frame (left)
    is cast to its declared column types before rendering, so the schema always
    steers the table.  With ``read_only_schema`` the schema is shown for
    reference only -- the runner must not change a curated workflow's contract.
    """
    row_schema = spec.schema
    prefix = f"{key}-{identifier}"
    data_key = f"{prefix}-data"
    if data_key not in st.session_state:
        st.session_state[data_key] = spec.example_table

    if not paths:
        return spec
    fields_label = ", ".join(".".join(map(str, field)) for field in spec.fields)
    st.caption(f"{identifier}: {fields_label} -> {list(paths)}")
    col1, col2 = st.columns(2)
    with col2:
        base_schema = (
            row_schema
            if isinstance(row_schema, dict)
            else infer_table_schema(st.session_state[data_key])
        )
        if read_only_schema:
            st.code(yaml.safe_dump(base_schema, sort_keys=False), language="yaml")
            new_schema = base_schema
        else:
            new_schema_text = st_ace(
                yaml.safe_dump(base_schema, sort_keys=False),
                language="yaml",
                height=_TABLE_ACE_HEIGHT,
                auto_update=False,
                key=f"{prefix}-schema",
            )
            parsed, parse_error = parse_yaml(new_schema_text)
            new_schema = (
                parsed if not parse_error and isinstance(parsed, dict) else row_schema
            )

    # The schema steers the table: cast the frame to its declared column types,
    # rebuilding the editor only when those types change.
    declared = column_dtypes(new_schema)
    types_key = f"{prefix}-types"
    retyped = st.session_state.get(types_key) != declared
    if retyped:
        st.session_state[types_key] = declared
        st.session_state[data_key], _ = coerce_frame(
            st.session_state[data_key], new_schema
        )

    with col1:
        change = column_controls(prefix)
        frame = editable_table(prefix, reset=bool(change) or retyped)
        frame, _ = coerce_frame(frame, new_schema)
        st.session_state[data_key] = frame
        example = nullify(frame.to_dict(as_series=False))

        spec = TableSpec(spec.fields, new_schema, example)
        for message in schema_errors(new_schema):
            st.error(f"table '{identifier}' schema: {message}")
        for message in spec.errors():
            st.error(f"table '{identifier}': {message}")
    return spec
