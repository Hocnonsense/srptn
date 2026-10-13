"""Pure helpers shared by the conversion core, store and preview.

Only a validation :class:`Issue` (re-exported from :mod:`..utils.issues`) and the
overlay join live here.  Conversion functions return a plain ``pl.DataFrame`` and
append problems to a caller-provided ``errors`` list -- errors are never bundled
with the table.  Everything is free of Streamlit and filesystem access.
"""

from typing import Sequence

import polars as pl

from ..utils.issues import Issue


def merge_overlay(
    table: pl.DataFrame,
    overlay: pl.DataFrame | None,
    keys: Sequence[str],
    errors: list[Issue] | None = None,
):
    """Left-join a user side table onto the generated table by explicit keys."""
    if overlay is None:
        return table
    if not keys:
        raise ValueError("must join with given column")

    both = []
    new = set()
    for column in overlay.columns:
        if column in keys:
            both.append(column)
        else:
            new.add(column)
    conflict = [c for c in table.columns if c in new]
    if conflict:
        error = "overlay columns clash with the table: " + (", ".join(conflict))
        if errors is None:
            raise ValueError(error)
        errors.append(Issue(error))

    final = table.join(overlay, on=both, how="left")
    if final.height != table.height:
        count_col = "count"
        while count_col in both:
            count_col += count_col
        duplicates = (
            overlay.group_by(both)
            .agg(pl.len().alias(count_col))
            .filter(pl.col(count_col) > 1)
        )
        descriptions = (
            duplicates.select(
                pl.concat_str(
                    [pl.format("{}={}", pl.lit(c), pl.col(c)) for c in both],
                    separator=", ",
                )
                + pl.format(" (×{})", pl.col(count_col))
            )
            .to_series()
            .to_list()
        )
        error = "overlay join changed row count, duplicated keys: " + "; ".join(
            descriptions
        )
        if errors is None:
            raise ValueError(error)
        errors.append(Issue(error))

    return final
