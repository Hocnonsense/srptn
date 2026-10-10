"""The declared-table sidecar: model, extraction and (de)serialization.

A table is identified by the key of the owning ``dict``.  Its ``fields`` are the
config paths it is associated with (several fields may share one table), and its
row ``schema``/``example`` describe what the runner-provided wide table must
look like.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, NamedTuple, IO

import polars as pl

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


def write_table(table: pl.DataFrame, path: Path):
    """Write a table by extension; unsupported extensions raise (no fallback)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        table.write_csv(path, separator="\t")
    elif suffix == ".csv":
        table.write_csv(path)
    elif suffix == ".xlsx":
        table.write_excel(path)
    else:
        raise ValueError(
            f"Unsupported file format: {suffix}. Supported formats are: "
            + ", ".join(TABLE_EXTENSIONS)
        )


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


def _json_type(dtype):
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
            column: {"type": _json_type(table.schema[column])}
            for column in table.columns
        },
    }


class TableSpec(NamedTuple):
    """A declared table: config field paths, row schema and columnar example."""

    fields: list
    schema: dict
    example: dict

    @property
    def example_table(self):
        return pl.DataFrame(self.example)

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
        errors: list[str] = []
        if self.schema:
            try:
                table = self.example_table
            except Exception as error:  # noqa: BLE001 - report bad example data
                errors.append(repr(error))
            else:
                for index, row in enumerate(table.iter_rows(named=True)):
                    for message in validation_errors(validate_values(row), self.schema):
                        errors.append(f"row {index}: {message}")
        return errors
