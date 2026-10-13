"""Row-schema coercion, inference and per-cell validation for tables.

Pure helpers over a Polars frame and a JSON-schema-like row schema: cast columns
to their declared dtypes, decode ``array`` cells, infer a schema from a frame and
validate cells.  No filesystem and no sidecar model live here.
"""

from __future__ import annotations

import json

from typing import Iterable, Mapping

import polars as pl

from .issues import Issue
from .schema_validation import validation_errors


def validate_values(row: Mapping):
    """Drop empty/null cells from a row, as Snakemake does before validation.

    Snakemake's ``validate`` excludes NULL values from each record, so an empty
    cell means "absent" (governed by the schema's ``required`` list) rather than
    a value that must match the declared type.
    """
    return {
        key: value for key, value in row.items() if value is not None and value != ""
    }


def table_errors(table: pl.DataFrame, schema: Mapping | None):
    """Validate ``table`` cells against the row ``schema``, column by column.

    Returns one :class:`Issue` per offending cell (with its row and column),
    plus a missing-column issue for each required column absent from the table.
    Array cells encoded as JSON strings are decoded before validation.
    """
    errors: list[Issue] = []
    if not schema or table is None:
        return errors
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        return errors
    arrays = set(array_fields(table.columns, schema))
    required = set(schema.get("required") or [])
    for column in table.columns:
        sub = properties.get(column)
        if not isinstance(sub, dict):
            continue
        for index, value in enumerate(table[column].to_list()):
            if value is None or value == "":
                if column in required:
                    errors.append(
                        Issue("required value missing", row=index, column=column)
                    )
                continue
            if column in arrays and isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            for message in validation_errors(value, sub):
                errors.append(Issue(message, row=index, column=column))
    for column in required:
        if column in table.columns:
            continue
        message = f"'{column}' is a required property"
        if table.height == 0:
            errors.append(Issue(message, column=column))
        for index in range(table.height):
            errors.append(Issue(message, row=index, column=column))
    return errors


def nullify(example: Mapping):
    """Canonicalize a columnar example: empty strings become ``None`` (absent).

    A table cell cannot distinguish ``""`` from missing, so the model keeps a
    single empty representation (``None``); this keeps the sidecar free of a
    mix of ``null`` and ``''``.
    """
    return {
        column: [None if value == "" else value for value in values]
        for column, values in example.items()
    }


def schema_columns(schema) -> list[str]:
    """The declared column names of a table row schema."""
    properties = schema.get("properties") if isinstance(schema, dict) else None
    return list(properties) if isinstance(properties, dict) else []


_PRIMITIVE_DTYPES = {
    "string": pl.Utf8,
    "integer": pl.Int64,
    "number": pl.Float64,
    "boolean": pl.Boolean,
}

_ARRAY_DTYPE = pl.List(pl.String)


def array_fields(fields: Iterable[str], schema: Mapping):
    """Declared ``array`` column names of a row schema."""
    properties = schema.get("properties") if isinstance(schema, dict) else {}
    if not properties:
        return
    for name in fields:
        sub = properties.get(name)
        if not isinstance(sub, dict) or sub.get("type") != "array":
            continue
        yield name


def column_dtypes(schema: dict):
    """Declared primitive column dtypes of a row schema (name -> Polars dtype)."""
    properties = schema.get("properties") if isinstance(schema, dict) else None
    dtypes: dict[str, type[pl.DataType]] = {}
    if not isinstance(properties, dict):
        return dtypes
    for name, sub in properties.items():
        if isinstance(sub, dict) and isinstance(sub.get("type"), str):
            dtype = _PRIMITIVE_DTYPES.get(sub["type"])
            if dtype is not None:
                dtypes[name] = dtype
    return dtypes


def coerce_frame(frame: pl.DataFrame, schema: dict):
    """Cast ``frame`` columns to the schema's declared column types.

    Primitive columns are cast as before; ``array`` columns encoded as a JSON
    string are decoded to a list.  A column whose values cannot be converted is
    left unchanged so validation can report it.  Returns ``(frame, changed)``.
    """
    changed = False
    for name in array_fields(frame.columns, schema):
        if frame.schema[name] == _ARRAY_DTYPE:
            continue
        if frame.schema[name] == pl.Utf8:
            try:
                frame = frame.with_columns(
                    pl.col(name).str.json_decode(_ARRAY_DTYPE).alias(name)
                )
            except Exception:  # noqa: BLE001 - unparseable values stay as-is
                continue
            changed = True
    for name, dtype in column_dtypes(schema).items():
        if name not in frame.columns or frame.schema[name] == dtype:
            continue
        if frame.schema[name] == pl.Utf8 and dtype != pl.Utf8:
            frame = frame.with_columns(pl.col(name).replace("", None))
        try:
            frame = frame.with_columns(pl.col(name).cast(dtype))
        except Exception:  # noqa: BLE001 - unparseable values stay as-is
            continue
        changed = True
    return frame, changed


def _json_type(dtype: pl.DataType):
    if dtype.is_integer():
        return "integer"
    if dtype.is_float():
        return "number"
    if dtype == pl.Boolean:
        return "boolean"
    return "string"


def infer_table_schema(table: pl.DataFrame):
    """Infer a row schema (an object of typed properties) from a table."""
    return {
        "type": "object",
        "properties": {
            column: _column_schema(table.schema[column]) for column in table.columns
        },
    }


def _column_schema(dtype: pl.DataType):
    if dtype.is_nested():
        return {"type": "array", "items": {"type": "string"}}
    return {"type": _json_type(dtype)}
