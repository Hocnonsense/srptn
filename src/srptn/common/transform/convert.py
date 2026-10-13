"""A deterministic plan to build one declared table.

A :class:`TableConvert` holds only the rule set and the overlay side table; the
source tables are supplied by the caller.  :meth:`build` merges those tables into
the long table, applies the rules, corrects pivot list columns against the
declared schema and joins the overlay, returning a plain ``pl.DataFrame`` and
appending any problem to a caller-provided ``errors`` list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import polars as pl

from ..utils.issues import Issue
from ..utils.table_schema import array_fields, table_errors
from .models import TransformRules

_LIST_STRING = pl.List(pl.String)
# TODO: unify _LIST_STRING logic.


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
        *,
        validate: bool = True,
    ):
        """Merge ``tables``, build the table and join the overlay.

        Problems are appended to ``errors``; when it is ``None`` the first
        problem raises ``ValueError``.  ``validate`` additionally appends the
        per-cell schema errors (callers that validate separately pass ``False``).
        Returns the resulting ``pl.DataFrame``.
        """
        if self.rules is None:
            if self.overlay is None:
                issue = Issue("no rules and no overlay to build from")
                if errors is None:
                    raise ValueError(str(issue))
                errors.append(issue)
                return pl.DataFrame({})
            return self.overlay
        long = self.rules.merge(dict(tables))
        table = self.rules.build(long, errors)
        table = unpack_by_schema(table, self.schema, errors)
        if self.overlay is not None:
            table = merge_overlay(table, self.overlay, self.rules.renamed_index, errors)
        if validate:
            schema_errors = list(table_errors(table, self.schema))
            if schema_errors:
                if errors is None:
                    raise ValueError(str(schema_errors[0]))
                errors.extend(schema_errors)
        return table


def unpack_by_schema(
    table: pl.DataFrame, schema: Mapping, errors: list[Issue] | None = None
):
    """Correct list columns to a single value unless the schema declares arrays.

    A ``List(String)`` column not declared ``array`` must hold at most one value
    per row: several values are an error, one becomes the value, none becomes
    null.  Declared ``array`` columns are kept as lists.
    """
    arrays = set(array_fields(table.columns, schema))
    for column in table.columns:
        if table.schema[column] != _LIST_STRING or column in arrays:
            continue
        lengths = table[column].list.len().to_list()
        failing = [index for index, length in enumerate(lengths) if (length or 0) > 1]
        if failing:
            rows = ", ".join(str(index) for index in failing)
            message = f"column '{column}' has multiple values in row(s) {rows}"
            if errors is None:
                raise ValueError(message)
            errors.append(Issue(message, column=column))
        table = table.with_columns(pl.col(column).list.first().alias(column))
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
