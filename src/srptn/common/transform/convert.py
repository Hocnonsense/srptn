"""A deterministic plan to build one declared table.

A :class:`TableConvert` holds only the rule set and the overlay side table; the
source tables are supplied by the caller.  :meth:`build` merges those tables into
the long table, applies the rules, joins the overlay and only then coerces the
result to the declared schema (collapsing pivot lists, casting primitives),
returning a plain ``pl.DataFrame`` and appending any problem to a caller-provided
``errors`` list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import polars as pl

from ..utils.issues import Issue
from ..utils.table_schema import coerce_frame, table_errors
from .models import TransformRules


@dataclass
class TableConvert:
    """How to build one declared table from supplied source tables.

    ``rules`` record how the tables are merged, filtered, pivoted and renamed;
    ``None`` with an overlay is the overlay-only case.  ``schema`` is the
    declared row schema used to correct pivot list columns to a single value (or
    report an error); it is not part of the saved rules.
    """

    schema: Mapping
    rules: TransformRules | None
    overlay: pl.DataFrame | None = None

    def build(
        self,
        tables: Mapping[str, pl.DataFrame],
        errors: list[Issue] | None = None,
    ):
        """Merge ``tables``, build the table and join the overlay.

        Problems are appended to ``errors``; when it is ``None`` the first
        problem raises ``ValueError``.  Returns the resulting ``pl.DataFrame``.
        """
        if self.rules is None:
            if self.overlay is None:
                issue = Issue("no rules and no overlay to build from")
                if errors is None:
                    raise ValueError(str(issue))
                errors.append(issue)
                return pl.DataFrame({})
            table = self.overlay
        else:
            long = self.rules.merge(dict(tables))
            table = self.rules.build(long, errors)
            if self.overlay is not None:
                table = merge_overlay(
                    table, self.overlay, self.rules.renamed_index, errors
                )
        # Align with the declared schema only after the overlay is joined, so the
        # overlay's own columns are coerced too and the join keys keep matching
        # types (the base table and the overlay are both still raw strings).
        table, _ = coerce_frame(table, self.schema, errors)
        schema_errors = list(table_errors(table, self.schema))
        if schema_errors:
            if errors is None:
                raise ValueError(str(schema_errors[0]))
            errors.extend(schema_errors)
        return table


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
