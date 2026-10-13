"""A deterministic plan to build one declared table.

A :class:`TableConvert` holds only the rule set and the overlay side table; the
source tables are supplied by the caller.  :meth:`build` merges those tables into
the long table, applies the rules, corrects pivot list columns against the
declared schema and joins the overlay, returning a plain ``pl.DataFrame`` and
appending any problem to a caller-provided ``errors`` list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import polars as pl

from ..utils.issues import Issue
from ..utils.workflow_tables import array_fields, table_errors
from .core import merge_overlay
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
            return self.overlay
        long = self.rules.merge(dict(tables))
        table = self.rules.build(long, errors)
        table = unpack_by_schema(table, self.schema, errors)
        if self.overlay is not None:
            table = merge_overlay(table, self.overlay, self.rules.renamed_index, errors)
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
