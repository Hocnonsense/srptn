"""Reusable sample-sheet editor.

A Dataset's metadata is one editable table: the first column is ``file`` (one
row per data file) and the remaining columns are free metadata.  The same
mechanism is used when creating a Dataset and when an analysis edits the
selected Datasets' metadata, so the two stay consistent:

- the table keeps in step with the files (new files add rows, emptied rows for
  gone files are dropped),
- an upload replaces it outright,
- ``column_controls`` / ``editable_table`` provide add/rename/remove/reorder and
  cell editing.

There is no hidden mapping: the file reference is the ``file`` column and every
other column is business metadata.
"""

from __future__ import annotations

from typing import Sequence

import polars as pl
import streamlit as st

from ..utils.polars_utils import load_data_table
from .table_editor import column_controls, editable_table

FILE_COLUMN = "file"
_EXTENSIONS = ("tsv", "csv", "xlsx")


def sample_sheet_editor(
    key: str, file_names: Sequence[str] | None, initial: pl.DataFrame | None = None
):
    """Render one editable sample sheet and return ``(sheet, errors)``.

    ``file_names`` is the external file list to keep the sheet in step with and
    validate against; pass ``None`` when the sheet itself is the source of truth
    (an analysis editing a Dataset's stored metadata).  ``initial`` seeds the
    sheet when no session state exists yet; otherwise a default
    ``file``/``sample`` sheet is generated from ``file_names``.  The returned
    ``sheet`` is ``None`` when there is nothing to edit.
    """
    data_key = f"{key}-data"
    source_key = f"{key}-source"
    reset = False

    upload = st.file_uploader("Sample Sheet", type=_EXTENSIONS, key=f"{key}-upload")
    if upload is not None:
        identity = ("upload", upload.name, upload.size)
        if st.session_state.get(source_key) != identity:
            loaded = load_data_table(upload, "upload")
            if loaded is None:
                return None, ["Failed to load sample sheet"]
            if FILE_COLUMN in loaded.columns:
                loaded = loaded.with_columns(pl.col(FILE_COLUMN).cast(pl.String))
            st.session_state[data_key] = loaded.with_columns(
                pl.col(pl.String).str.strip_chars()
            )
            st.session_state[source_key] = identity
            reset = True
    else:
        if (
            st.session_state.get(source_key) != ("seeded",)
            or data_key not in st.session_state
        ):
            seed = initial if initial is not None else default_sheet(file_names or [])
            if seed is None:
                return None, []
            st.session_state[data_key] = seed
            st.session_state[source_key] = ("seeded",)
            reset = True
        if file_names is not None:
            synced = sync_sheet(st.session_state[data_key], file_names)
            if synced is not None:
                st.session_state[data_key] = synced
                reset = True

    change = column_controls(key)
    st.caption("Sample sheet (first column is 'file')")
    sheet = editable_table(key, reset=reset or bool(change))
    return sheet, sheet_errors(sheet, file_names)


def default_sheet(file_names: Sequence[str]):
    """A fresh ``file`` + ``sample`` sheet, or ``None`` without files."""
    if file_names:
        return pl.DataFrame(
            {FILE_COLUMN: list(file_names)}, schema={FILE_COLUMN: pl.String}
        ).with_columns(sample=pl.col(FILE_COLUMN))


def sync_sheet(sheet: pl.DataFrame, file_names: Sequence[str]):
    """Align a sheet's rows with the files; ``None`` when nothing changed.

    A new file gets a row with every column except ``file`` empty; a row whose
    file is gone is dropped only while its other columns are all empty, so a row
    that still holds data is kept (and later reported by :func:`sheet_errors`).
    Duplicate rows are preserved.
    """
    columns = list(sheet.columns)
    if FILE_COLUMN not in columns:
        return None
    known = set(file_names)
    others = [column for column in columns if column != FILE_COLUMN]
    kept = []
    changed = False
    for row in sheet.iter_rows(named=True):
        if row[FILE_COLUMN] in known or not all(
            _blank(row[column]) for column in others
        ):
            kept.append(row)
        else:
            changed = True
    present = {row[FILE_COLUMN] for row in kept}
    for name in file_names:
        if name not in present:
            kept.append({FILE_COLUMN: name} | dict.fromkeys(others))
            changed = True
    if changed:
        return pl.DataFrame(kept, schema=sheet.schema)


def sheet_errors(sheet: pl.DataFrame, file_names: Sequence[str] | None):
    """Reasons the sheet cannot be used, if any.

    The first column must be named ``file`` and its entries non-empty, unique
    and, when ``file_names`` is given, matching exactly the files (no unknown
    entry, no unused file).  Each row must also carry at least one non-empty
    value besides ``file``.
    """
    errors: list[str] = []
    if sheet.width == 0:
        return errors
    if sheet.columns[0] != FILE_COLUMN:
        return [f"The first column must be named '{FILE_COLUMN}'."]

    others = sheet.columns[1:]
    known = set(file_names) if file_names is not None else None
    seen = set()
    for index, row in enumerate(sheet.iter_rows(named=True), start=1):
        entry = row[FILE_COLUMN]
        if entry is None or entry == "":
            errors.append(f"Row {index}: empty '{FILE_COLUMN}' entry.")
            continue
        if entry in seen:
            errors.append(f"Duplicate file entry: {entry}")
        else:
            seen.add(entry)
            if known is not None and entry not in known:
                errors.append(f"Unknown file entry: {entry}")
        if all(_blank(row[column]) for column in others):
            errors.append(f"Row {index}: no value besides '{FILE_COLUMN}'.")
    if known is not None:
        missing = sorted(known - seen)
        if missing:
            errors.append("Missing file entries: " + ", ".join(missing))
    return errors


def _blank(value):
    return value is None or str(value).strip() == ""
