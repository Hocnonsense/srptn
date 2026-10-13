"""Declarative rules for turning Dataset metadata into a workflow sample table.

The rule set is small and deterministic: merge the chosen source tables over a
column set, filter rows by typed conditions, optionally pivot ``pivot_columns``
(values collected as lists) and rename the result.  Constants and derived
values are out of scope -- they belong to the workflow ``config``/``code`` or to
the overlay side table.  YAML is used as the on-disk format, reusing the
project's :class:`CustomSafeLoader`/:class:`CustomSafeDumper`.
"""

from __future__ import annotations

import operator
import types

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Callable, ClassVar, Union, get_args, get_origin, get_type_hints

from ..utils.issues import Issue

import polars as pl


@dataclass(frozen=True)
class Condition:
    """A single, typed filter over the fixed input snapshot."""

    column: str
    op: str
    value: str | None
    negate: bool = False

    SUPPORTED_OPS: ClassVar[dict[str, Callable[[pl.Expr, Any], pl.Expr]]] = {
        "==": operator.eq,
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
        "in": lambda column, value: column.is_in(_as_list(value)),
        "match": lambda column, value: column.cast(pl.String).str.contains(
            str(value), strict=False
        ),
    }

    def expression(self, dtype: pl.DataType | None = None):
        """Build the Polars expression for this condition.

        ``dtype`` is the column's type; a widget string is coerced to it for
        the comparison operators.  ``negate`` inverts the whole comparison.
        Raises ``ValueError`` for an unsupported operator so the caller can
        report it.
        """
        if self.op not in self.SUPPORTED_OPS:
            raise ValueError(f"unsupported condition operator '{self.op}'")
        column = pl.col(self.column)
        value = _typed_value(self.value, dtype)
        expression = self.SUPPORTED_OPS[self.op](column, value)
        return ~expression if self.negate else expression


def _as_list(value):
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _typed_value(value, dtype: pl.DataType | None):
    """Coerce a widget string to the column's type for comparison."""
    if value is None or dtype is None:
        return value
    if isinstance(value, (list, tuple, set)):
        return [_typed_value(item, dtype) for item in value]
    if not isinstance(value, str):
        return value
    text = value.strip()
    if dtype.is_integer():
        try:
            return int(text)
        except ValueError:
            return value
    if dtype.is_float():
        try:
            return float(text)
        except ValueError:
            return value
    if dtype == pl.Boolean:
        return text.lower() in {"1", "true", "yes", "y", "t"}
    return value


@dataclass
class TransformRules:
    """The complete, replayable rule set for one generated sample table."""

    sources: tuple[str, ...]
    columns: tuple[str, ...]
    pivot_values: tuple[str, ...]
    conditions: tuple[Condition, ...] = ()
    pivot_columns: tuple[str, ...] = ()
    renames: dict[str, str] = field(default_factory=dict)

    def merge(self, tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
        """Concatenate the source tables over ``columns``."""
        frames = [tables[name] for name in self.sources]
        aligned = []
        for frame in frames:
            missing = [column for column in self.columns if column not in frame.columns]
            if missing:
                frame = frame.with_columns(
                    [pl.lit(None).alias(column) for column in missing]
                )
            aligned.append(frame.select(self.columns))
        return pl.concat(aligned, how="diagonal_relaxed")

    def filter(self, long: pl.DataFrame, errors: list[Issue] | None = None):
        """Filter the fixed snapshot by explicit conditions."""
        table = long
        for condition in self.conditions:
            try:
                expression = condition.expression(table.schema.get(condition.column))
            except ValueError as error:
                if errors is None:
                    raise error
                errors.append(Issue(str(error), column=condition.column))
                continue
            table = table.filter(expression)
        return table

    @property
    def pivot_indexes(self):
        exclude = set(self.pivot_columns) | set(self.pivot_values)
        return [column for column in self.columns if column not in exclude]

    def pivot(self, inputs: pl.DataFrame):
        """Pivot ``pivot_columns`` into columns, keeping values as lists.

        ``aggregate_function=pl.element().implode()`` makes every generated
        column ``List(String)`` (an empty list when a cell has no value).
        """
        return inputs.pivot(
            index=self.pivot_indexes,
            on=list(self.pivot_columns),
            values=self.pivot_values,
            aggregate_function=pl.element().implode(),
        )

    def renamed(self, table: pl.DataFrame):
        """Rename columns according to ``renames``."""
        return table.rename(self.renames)

    @property
    def renamed_index(self):
        """The row keys after renaming, for joining the overlay."""
        return [self.renames.get(column, column) for column in self.pivot_indexes]

    def build(self, long: pl.DataFrame, errors: list | None = None):
        """Filter, (optionally) pivot and rename the merged long table."""
        table = self.filter(long, errors)
        if self.pivot_columns:
            table = self.pivot(table)
        return self.renamed(table)

    def to_dict(self):
        """Return a plain YAML/JSON-serializable dict."""
        return to_data(self)

    @classmethod
    def from_dict(cls, data: dict):
        """Rebuild a rule set from :meth:`to_dict` output."""
        return from_data(cls, data)


def to_data(value):
    """Recursively turn dataclasses and tuples into plain containers."""
    # TODO: why not using public package?
    if is_dataclass(value):
        return {f.name: to_data(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {key: to_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_data(item) for item in value]
    return value


def from_data(cls, data):
    """Rebuild dataclasses produced by :func:`to_data`."""
    if data is None:
        return None
    return _convert(cls, data)


def _convert(cls, values: dict):
    hints = get_type_hints(cls)
    kwargs = {}
    for f in fields(cls):
        if f.name in values:
            kwargs[f.name] = _coerce(hints[f.name], values[f.name])
    return cls(**kwargs)


def _coerce(tp, value):
    if value is None:
        return None
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is None:
        if is_dataclass(tp):
            return _convert(tp, value)
        return value
    if type(None) in args:
        inner = next(a for a in args if a is not type(None))
        return _coerce(inner, value)
    if origin in (list, tuple):
        if origin is tuple and args and args[-1] is not Ellipsis:
            return tuple(_coerce(a, v) for a, v in zip(args, value, strict=True))
        inner = args[0] if args else Any
        items = [_coerce(inner, item) for item in value]
        return tuple(items) if origin is tuple else items
    if origin in (dict,) or origin is Union or origin is types.UnionType:
        return value
    return value
