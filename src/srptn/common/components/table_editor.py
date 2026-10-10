"""Reusable editable-table widgets.

``column_controls`` renders icon add/rename/remove-column popovers and threads
the frame through them (plus any ``extras``); ``editable_table`` wraps
``st.data_editor``.  Both are plain Streamlit widgets shared by the analysis and
curation flows and carry no schema or persistence logic.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import polars as pl
import streamlit as st

Control = Callable[[str, pl.DataFrame], tuple[pl.DataFrame, Any] | None]
""" A control takes the widget key and the current frame and returns the
(possibly updated) frame plus a change payload, or ``None`` when it did not
fire.
"""


def column_controls(
    key: str,
    frame: pl.DataFrame,
    *,
    controls: Mapping[str, Control] | None = None,
    extras: Mapping[str, Control] | None = None,
):
    """Render icon add/rename/remove-column popovers for ``frame``.

    Returns the (possibly modified) table together with the changes applied,
    keyed by control name (``add``/``rename``/``remove``, plus any ``extras``
    key).  The mapping is empty when nothing changed.

    ``controls`` replaces the three default controls; ``extras`` renders
    additional controls next to them.  Each follows :data:`Control` and is
    threaded the frame produced so far.
    """
    changes: dict[str, Any] = {}
    calls = dict(controls or _default_controls) | dict(extras or {})
    holders = st.columns(len(calls))
    for holder, call in zip(holders, calls):
        with holder:
            ret = calls[call](key, frame)
        if ret is not None:
            frame, changes[call] = ret
    return frame, changes


def editable_table(
    key: str,
    frame: pl.DataFrame,
    *,
    column_config: Mapping | None = None,
    on_change: Callable | None = None,
    args: tuple | None = None,
):
    """Shared ``st.data_editor`` call; returns the edit as a Polars frame."""
    edited = st.data_editor(
        frame.to_pandas(),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=key,
        column_config=column_config,
        on_change=on_change,
        args=args,
    )
    return pl.from_pandas(edited)


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


_default_controls = {
    "add": _add_column,
    "rename": _rename_column,
    "remove": _delete_column,
}
