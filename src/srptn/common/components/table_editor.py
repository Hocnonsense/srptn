"""Reusable editable-table widgets.

A table is identified by ``key``; its current data lives in
``st.session_state[f"{key}-data"]``.  ``column_controls`` renders icon
add/rename/remove/reorder popovers that edit that entry (plus any ``extras``);
``editable_table`` wraps ``st.data_editor`` and returns the edited frame.  Both
are plain Streamlit widgets shared by the analysis and curation flows and carry
no schema or persistence logic.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import polars as pl
import streamlit as st
from streamlit_sortables import sort_items

Control = Callable[[str, pl.DataFrame], tuple[pl.DataFrame, Any] | None]
""" A control takes the widget key and the current frame and returns the
(possibly updated) frame plus a change payload, or ``None`` when it did not
fire.
"""


def column_controls(
    key: str,
    *,
    controls: Mapping[str, Control] | None = None,
    extras: Mapping[str, Control] | None = None,
):
    """Render icon column popovers for ``st.session_state[f"{key}-data"]``.

    Returns the changes applied, keyed by control name (``add``/``rename``/
    ``remove``/``move``, plus any ``extras`` key).  The mapping is empty when
    nothing changed.

    ``controls`` replaces the default controls; ``extras`` renders additional
    controls next to them.  Each follows :data:`Control` and is threaded the
    current ``{key}-data`` frame.
    """
    changes: dict[str, Any] = {}
    calls = dict(controls or _default_controls) | dict(extras or {})
    holders = st.columns(len(calls))
    for holder, call in zip(holders, calls):
        with holder:
            ret = calls[call](key, st.session_state[f"{key}-data"])
        if ret is not None:
            st.session_state[f"{key}-data"], changes[call] = ret
    return changes


def editable_table(
    key: str,
    *,
    column_config: Mapping | None = None,
    drop_empty: bool = True,
    reset: bool = False,
) -> pl.DataFrame:
    """Render ``st.data_editor`` for ``st.session_state[f"{key}-data"]``.

    The current data lives in ``{key}-data``; the edited result is written back
    there and returned.  Edits accumulate against a separate stable **base**
    (``{key}-base``) rather than re-feeding ``{key}-data`` as the editor input,
    which would make edits lag by one run.  Pass ``reset=True`` when the table
    is replaced programmatically (column change, upload, fill, clear) so the
    base is re-seeded and the widget rebuilt.

    With ``drop_empty`` (the default) rows whose cells are all blank are
    removed, so empty rows added in the editor are not persisted.
    """
    data_key = f"{key}-data"
    base_key = f"{key}-base"
    revision_key = f"{key}-revision"
    if reset or base_key not in st.session_state:
        st.session_state[base_key] = st.session_state[data_key]
        st.session_state[revision_key] = st.session_state.get(revision_key, 0) + 1
    edited = st.data_editor(
        st.session_state[base_key].to_pandas(),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"{key}-{st.session_state[revision_key]}",
        column_config=column_config,
    )
    result = pl.from_pandas(edited)
    result = _drop_empty_rows(result) if drop_empty else result
    st.session_state[data_key] = result
    return result


def _drop_empty_rows(frame: pl.DataFrame) -> pl.DataFrame:
    """Drop rows where every cell is null or blank."""
    if frame.height == 0 or not frame.columns:
        return frame
    blank = [
        pl.col(column).is_null()
        | (pl.col(column).cast(pl.Utf8).str.strip_chars() == "")
        for column in frame.columns
    ]
    return frame.filter(~pl.all_horizontal(blank))


def _add_column(key: str, frame: pl.DataFrame):
    options = list(frame.columns)
    with st.popover("", icon=":material/add:", help="Add a column"):
        name = st.text_input("Add column", key=f"{key}-new-column")
        clicked = st.button("Add", key=f"{key}-add-column")
    name = (name or "").strip()
    if clicked and name and name not in options:
        return frame.with_columns(pl.Series(name, [""] * frame.height)), name


def _rename_column(key: str, frame: pl.DataFrame):
    options = list(frame.columns)
    with st.popover("", icon=":material/edit:", help="Rename a column"):
        if options:
            selected = st.selectbox(
                "Select column to rename", options, key=f"{key}-rename-column"
            )
            renamed = st.text_input("Rename to", key=f"{key}-rename-column-text")
            clicked = st.button("Rename", key=f"{key}-rename-column-button")
        else:
            st.caption("No columns to rename.")
            selected, renamed, clicked = None, "", False
    new_name = (renamed or "").strip()
    if clicked and new_name and new_name not in options and selected in frame.columns:
        return frame.rename({selected: new_name}), (selected, new_name)


def _delete_column(key: str, frame: pl.DataFrame):
    options = list(frame.columns)
    with st.popover("", icon=":material/remove:", help="Remove a column"):
        if options:
            selected = st.selectbox(
                "Select column to remove", options, key=f"{key}-remove-column"
            )
            clicked = st.button("Remove", key=f"{key}-remove-column-button")
        else:
            st.caption("No columns to remove.")
            selected, clicked = None, False
    if clicked and selected in frame.columns:
        return frame.drop(selected), selected


def _move_column(key: str, frame: pl.DataFrame):
    options = list(frame.columns)
    with st.popover("", icon=":material/swap_horiz:", help="Reorder columns"):
        if len(options) > 1:
            order = sort_items(options, direction="vertical", key=f"{key}-column-order")
        else:
            st.caption("Need at least two columns to reorder.")
            order = options
    if list(order) != options:
        return frame.select(list(order)), order


_default_controls = {
    "add": _add_column,
    "rename": _rename_column,
    "remove": _delete_column,
    "move": _move_column,
}
