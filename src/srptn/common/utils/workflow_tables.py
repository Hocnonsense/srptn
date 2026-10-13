"""The declared-table sidecar: model, extraction and (de)serialization.

A table is identified by the key of the owning ``dict``.  Its ``fields`` are the
config paths it is associated with (several fields may share one table), and its
row ``schema``/``example`` describe what the runner-provided wide table must
look like.
"""

from __future__ import annotations

import json

from pathlib import Path
from typing import Iterable, Mapping, NamedTuple, IO

import polars as pl

from .issues import Issue
from .schema_validation import validation_errors
from .yaml_utils import dump_yaml, load_yaml

TABLE_EXTENSIONS = (".tsv", ".csv", ".xlsx")


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


def _get_by_path(config, path: list[str], default=None):
    """Resolve a nested field path in a config mapping."""
    # TODO: support file patterns
    node = config
    for name in path:
        if not isinstance(node, Mapping) or name not in node:
            return default
        node = node[name]
    return node


def read_table(
    source: str | Path | IO[bytes] | bytes,
    schema: Mapping[str, pl.DataType | type[pl.DataType]] | None = None,
    *,
    suffix: str | None = None,
    infer: bool = False,
) -> pl.DataFrame | None:
    """Read a table by extension, or ``None`` when unreadable/unsupported.

    ``source`` is a path or a binary buffer/-stream; pass ``suffix`` when it is
    not a path.  ``schema`` gives strict per-column dtype overrides; ``infer``
    selects how the remaining columns are read.  Combining them yields four
    modes:

    ============ ===================================================
    (None, False) every column as string (``infer_schema_length=0``),
                  the ``dtype=str`` convention of Snakemake sample
                  sheets: identifiers such as ``unit`` stay strings
    (None, True)  Polars' default type inference
    (schema, *)   ``schema`` columns keep their dtype; the rest follow
                  ``infer`` (strings or inferred)
    ============ ===================================================
    """
    kwargs: dict = dict(
        schema_overrides=dict(schema) if schema else None,
        infer_schema_length=None if infer else 0,
    )
    suffix = (suffix or getattr(source, "suffix", "")).lower()
    try:
        if suffix == ".tsv":
            return pl.read_csv(source, separator="\t", **kwargs)
        if suffix == ".csv":
            return pl.read_csv(source, **kwargs)
        if suffix == ".xlsx":
            return pl.read_excel(source, **kwargs)
    except Exception:
        return None
    return None


def _suffix_table_fields(config):
    """Find config leaves whose value is a table file path (by extension)."""
    found: list[tuple[list[str], str]] = []

    def walk(node, path: list[str]):
        if not isinstance(node, Mapping):
            return
        for key, value in node.items():
            current = [*path, str(key)]
            if isinstance(value, Mapping):
                walk(value, current)
            elif isinstance(value, str) and value.endswith(TABLE_EXTENSIONS):
                found.append((current, value))

    walk(config, [])
    return found


def _inline_table(data_path: Path | None, value: str):
    schema = None
    example = {}
    if data_path is not None:
        name = Path(value).name.rsplit(".", 1)[0]
        for ext in ("yaml", "yml", "json"):
            candidate = data_path / "workflow" / "schemas" / f"{name}.schema.{ext}"
            if candidate.exists():
                schema = load_yaml(candidate.read_text())
                if not isinstance(schema, dict):
                    raise ValueError(f"Schema {candidate} is not a mapping")
                break
        table = read_table(data_path / value)
        if table is not None:
            example = table.to_dict(as_series=False)
    return (schema or {"type": "object"}, example)


def build_tables(config, data_path: Path | None = None):
    """Build the table sidecar: id -> :class:`TableSpec`.

    Config leaves whose value is a table file path are grouped by file
    basename, so several fields sharing a table share one id; the first field's
    file is used to inline the row schema and a columnar example.
    """
    grouped: dict[str, list[list[str]]] = {}
    first_value: dict[str, str] = {}
    for field_path, value in _suffix_table_fields(config):
        identifier = Path(value).name.rsplit(".", 1)[0] or "table"
        grouped.setdefault(identifier, []).append(list(field_path))
        first_value.setdefault(identifier, value)

    tables: dict[str, TableSpec] = {}
    for identifier, fields in grouped.items():
        schema, example = _inline_table(data_path, first_value[identifier])
        tables[identifier] = TableSpec(fields=fields, schema=schema, example=example)
    return tables


def add_table_fields(
    config,
    fields: list[str],
    tables: dict[str, TableSpec],
    data_path: Path | None = None,
):
    """Merge ``paths`` into ``tables`` as table field bindings, by file basename.

    Each path is a dot-separated config key; its value is resolved in ``config``
    and the table id is the basename stem of that file.  Paths resolving to the
    same id share one table, whose row schema and example come from the first
    field's file (mirroring :func:`build_tables`).  Unknown or non-string paths
    are skipped.
    """
    value = _get_by_path(config, fields)
    if not fields or not isinstance(value, str) or not value:
        return
    identifier = Path(value).name.rsplit(".", 1)[0] or "table"
    spec: TableSpec | None = tables.get(identifier)
    if spec is None:
        schema, example = _inline_table(data_path, value)
        tables[identifier] = TableSpec(fields=[fields], schema=schema, example=example)
    elif fields not in spec.fields:
        tables[identifier] = TableSpec(
            fields=[*spec.fields, fields], schema=spec.schema, example=spec.example
        )


def tables_from_data(data: str):
    """Rebuild a table sidecar from its YAML text."""
    return {
        str(identifier): TableSpec(**value)
        for identifier, value in (load_yaml(data) or {}).items()
    }


def tables_to_data(tables: Mapping[str, TableSpec]):
    """Serialize a table sidecar to YAML text."""
    return dump_yaml(
        {identifier: spec._asdict() for identifier, spec in tables.items()},
    )


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


class TableSpec(NamedTuple):
    """A declared table: config field paths, row schema and columnar example."""

    fields: list
    schema: dict
    example: dict

    @property
    def example_table(self):
        example = (
            nullify(self.example)
            if self.example
            else {column: [] for column in schema_columns(self.schema)}
        )
        frame, _ = coerce_frame(pl.DataFrame(example), self.schema)
        return frame

    def paths(self, config):
        """The distinct config values (file paths) for this table's fields."""
        paths: list[str] = []
        for field in self.fields:
            value = _get_by_path(config, field)
            if isinstance(value, str) and value and value not in paths:
                paths.append(value)
        return paths

    def errors(self):
        """Validate the columnar example against the row schema."""
        if self.schema:
            try:
                table = self.example_table
            except Exception as error:  # noqa: BLE001 - report bad example data
                yield repr(error)
            else:
                for issue in table_errors(table, self.schema):
                    yield issue


def table_path_frames(tables: Mapping[str, TableSpec], config):
    """Expand each declared table's example to every config path it binds to."""
    provided: dict[str, pl.DataFrame] = {}
    for spec in tables.values():
        table = spec.example_table
        for path in spec.paths(config):
            provided[path] = table
    return provided
