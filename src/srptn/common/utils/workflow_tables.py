"""The declared-table sidecar: model, extraction and (de)serialization.

A table is identified by the key of the owning ``dict``.  Its ``fields`` are the
config paths it is associated with (several fields may share one table), and its
row ``schema``/``example`` describe what the runner-provided wide table must look
like.  Schema coercion/validation lives in :mod:`table_schema` and flat-format
reading in :mod:`polars_utils`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, NamedTuple

import polars as pl

from .polars_utils import TABLE_EXTENSIONS, read_table
from .table_schema import coerce_frame, nullify, schema_columns, table_errors
from .yaml_utils import dump_yaml, load_yaml


def _get_by_path(config, path: list[str], default=None):
    """Resolve a nested field path in a config mapping."""
    # TODO: support file patterns
    node = config
    for name in path:
        if not isinstance(node, Mapping) or name not in node:
            return default
        node = node[name]
    return node


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
