"""Preview helpers for tables selected from an Analysis.

The page only offers paths returned by :meth:`Analysis.workflow_files`; reading
and suffix detection are delegated to :mod:`..utils.table_utils`.
"""

from __future__ import annotations

import math

from typing import TYPE_CHECKING

import polars as pl

from ..data import FileType
from ..utils.table_utils import read_table, table_suffix

if TYPE_CHECKING:
    from ..data.workspace import Workspace


def read_table_full(workspace: "Workspace", logical_path: str):
    """Read a full table from the workspace, or ``None`` if it is unavailable."""
    try:
        with workspace.load_file(logical_path, FileType.DATA) as handle:
            return read_table(
                handle,
                suffix=table_suffix(logical_path),
                infer=True,
            )
    except OSError:
        return None


def vega_schema(frame: pl.DataFrame | pl.Schema):
    """Map a frame or Polars schema to Vega-Lite types.

    Returns ``(schema, skipped)``.  ``frame.schema`` is a Polars dtype mapping,
    not a Vega-Lite encoding schema; this function performs that translation.
    """
    source = frame.schema if isinstance(frame, pl.DataFrame) else frame
    schema: dict[str, str] = {}
    skipped: list[str] = []
    for name, dtype in source.items():
        if dtype.is_numeric():
            schema[name] = "quantitative"
        elif dtype.is_temporal():
            schema[name] = "temporal"
        elif dtype == pl.Boolean or dtype in (
            pl.String,
            pl.Categorical,
            pl.Enum,
            pl.Null,
        ):
            schema[name] = "nominal"
        else:
            skipped.append(name)
    return schema, skipped


def preview_records(frame: pl.DataFrame, limit: int | None = None) -> list[dict]:
    """Return JSON-safe records for an in-browser preview."""
    frame = frame.head(limit) if limit is not None else frame
    casts = []
    for name, dtype in frame.schema.items():
        if dtype == pl.Decimal:
            casts.append(pl.col(name).cast(pl.Float64))
        elif not dtype.is_numeric() and dtype != pl.Boolean:
            casts.append(pl.col(name).cast(pl.String))
    if casts:
        frame = frame.with_columns(casts)
    records = frame.to_dicts()
    for record in records:
        for name, value in record.items():
            if isinstance(value, float) and not math.isfinite(value):
                record[name] = None
    return records
