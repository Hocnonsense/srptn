"""The Datasets' long-table inputs for the conversion editors.

A Dataset's metadata *is* a long table: the ``file`` column holds the file name
and every other column is business metadata.  Its identity is the key
``(address, file)``.  This module edits each selected Dataset's metadata with the
same sample-sheet mechanism used when creating a Dataset, then stamps the key
columns (``datasetid``/``filename``/``source_row_id``/``file_id``) and
concatenates them into the long table the editors consume -- no hidden mapping
or unpivot, so the user can select columns, concatenate and reshape directly.
"""

from __future__ import annotations

import os

from typing import Sequence, TYPE_CHECKING

import polars as pl
import streamlit as st


from ..data import FileType
from .sample_sheet import sample_sheet_editor

if TYPE_CHECKING:
    from ..data.entities.dataset import Dataset
    from ..data.workspace import Workspace


def dataset_long_table(key: str, datasets: "Sequence[Dataset]"):
    """Edit each Dataset's metadata and return ``{address: sheet}``.

    The ``file`` column is left as the sheet's own name; the page keys the
    tables with :func:`keyed_tables`/func:`make_key`.  ``None`` when no selected
    Dataset has files or a sheet to edit.
    """
    tables: dict[str, pl.DataFrame] = {}
    for dataset in datasets:
        if dataset.sheet is not None:
            initial = dataset.sheet
            editor_files = None
        else:
            editor_files = dataset.list_files(FileType.DATA)["name"].to_list()
            if not editor_files:
                continue
            initial = None
        st.markdown(f"**{dataset.address}** (dataset metadata)")
        sheet, sheet_errors = sample_sheet_editor(
            f"{key}-{dataset.address}", editor_files, initial
        )
        if sheet is None or sheet_errors:
            for message in sheet_errors:
                st.error(message)
            continue
        tables[str(dataset.address)] = sheet

    return tables


def make_key(address: str, file_column: pl.Expr):
    """Preview key: ``address//name`` (``//`` delimits the address)."""
    return pl.lit(address + "/") + file_column


def make_realpath(workspace: "Workspace"):
    """Final key: the file's real path relative to ``base``.

    ``file_column`` holds a name relative to ``data_root/address``; the result
    is what the Analysis working directory (``base``) can open.
    """
    base = workspace.data_path
    data_root = workspace.store.base_data

    def inner(address: str, file_column: pl.Expr):
        full = pl.lit(os.path.join(str(data_root), address) + "/") + file_column
        return full.map_elements(
            lambda path: os.path.relpath(path, base), return_dtype=pl.String
        )

    return inner
