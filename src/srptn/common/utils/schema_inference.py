"""Inferring a JSON schema from a config/table dictionary.

The inferred schema uses the app-specific ``"missing"`` type for empty values,
which :func:`..schema_validation.sanitize_schema` drops before validation.
"""

from __future__ import annotations

from math import isnan

import polars as pl


def get_nonan_index(value: pl.Series | list):
    """Index of the first non-NaN value, or ``None`` when all are NaN/empty."""

    def isna(item):
        return not item or (isinstance(item, float) and isnan(item))

    for index, item in enumerate(value):
        if not isna(item):
            return index
    return None


def infer_schema(config: dict):
    """Infer a JSON schema from a configuration dictionary."""
    schema = {"type": "object", "properties": {}}
    for key, value in config.items():
        if isinstance(value, dict):
            schema["properties"][key] = infer_schema(value)
        else:
            schema["properties"][key] = infer_type(value)
    return schema


def infer_type(value: pl.Series | list | bool | float | str | None) -> dict:
    """Infer the JSON schema type for a single value."""
    match value:
        case value if isinstance(value, pl.Series):
            if len(value) == 0:
                return {"type": "missing"}
            index = get_nonan_index(value)
            value_schema = {
                "type": "array",
                "items": (
                    infer_type(value[index])
                    if index is not None
                    else {"type": "missing"}
                ),
            }
        case value if isinstance(value, list):
            index = get_nonan_index(value)
            value_schema = {
                "type": "array",
                "items": (
                    infer_type(value[index])
                    if index is not None
                    else {"type": "missing"}
                ),
            }
        case bool(value):
            value_schema = {"type": "boolean"}
        case int(value):
            value_schema = {"type": "integer"}
        case float(value):
            value_schema = {"type": "number"}
        case str(value):
            value_schema = {"type": "string"}
        case value:
            value_schema = {"type": "missing"}
    return value_schema
