"""Pure helpers for the workflow curation (publisher) flow.

The maintainer writes top-level Python *code* (not a function).  At run time
the platform executes it with the runner's config injected as ``config`` and
reads the transformed value back, then writes it to the workflow's config file.
The deployed Snakefile is left untouched.  These helpers also validate configs
against JSON schemas and locate table-valued config entries.
"""

from __future__ import annotations

import io
import tempfile

from contextlib import chdir, contextmanager
from functools import cache
from pathlib import Path

from typing import Any, Mapping, NamedTuple, overload
import polars as pl
import jsonschema.validators
import yaml


from .yaml_utils import SCIENTIFIC_FLOAT, CustomSafeDumper, CustomSafeLoader

TABLE_EXTENSIONS = (".tsv", ".csv", ".xlsx")


def load_yaml(text: str):
    """Parse YAML using the project loader (keeps scientific floats as strings)."""
    return yaml.load(text, Loader=CustomSafeLoader)


@contextmanager
def config_workdir():
    """A throw-away working directory for running the config code."""
    with tempfile.TemporaryDirectory() as temporary:
        yield Path(temporary)


def run_config_code(code: str, config: dict, cwd: Path) -> dict:
    """Execute the maintainer code with ``config`` injected and return it.

    The code runs with the working directory set to ``cwd`` (a temp dir for
    preview, the workspace data folder at run time), so it may read and write
    relative files.  Only the transformed ``config`` is returned; use
    :func:`collect_files` to inspect anything the code created.
    """
    namespace = {"config": config}
    with chdir(cwd):
        exec(code, namespace)  # noqa: S102 deliberate execution of curator code
    return namespace["config"]


def collect_files(root: Path):
    """Read every file under ``root`` as ``relative path -> bytes``."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@overload
def sanitize_schema(value: Mapping) -> dict: ...
@overload
def sanitize_schema(value: list) -> list: ...
@overload
def sanitize_schema(value: None) -> None: ...
def sanitize_schema(value):
    """Drop the app-specific ``"missing"`` type so jsonschema accepts the schema."""
    if isinstance(value, dict):
        result = {key: sanitize_schema(item) for key, item in value.items()}
        if result.get("type") == "missing":
            result.pop("type")
        return result
    if isinstance(value, list):
        return [sanitize_schema(item) for item in value]
    return value


@cache
def _extended_validator(base):
    def _is_number(type_checker, value):
        """A ``number`` also accepts scientific-notation strings.

        The project YAML loader keeps scientific floats as strings to preserve
        their exact form, so ``type: number`` must accept them.
        """
        if isinstance(value, str):
            return bool(SCIENTIFIC_FLOAT.match(value))
        return not isinstance(value, bool) and isinstance(value, (int, float))

    return jsonschema.validators.extend(
        base, type_checker=base.TYPE_CHECKER.redefine("number", _is_number)
    )


def validation_errors(instance, schema: Mapping | None) -> list[str]:
    """Return all jsonschema violations as ``"path: message"`` strings."""
    if not schema:
        return []
    schema = sanitize_schema(schema)
    base = jsonschema.validators.validator_for(schema)
    validator = _extended_validator(base)(schema)
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
        f"{error.message}"
        for error in errors
    ]


def transform_errors(
    code: str,
    config: Any,
    external_schema: Mapping | None,
    internal_schema: Mapping | None,
    cwd: Path,
):
    """Run the maintainer code in ``cwd`` and validate its output.

    Returns ``(produced, errors)``: the produced config and the combined
    errors -- the runner config against the external schema, and the produced
    config against the upstream internal schema.
    """
    errors = validation_errors(config, external_schema)
    try:
        produced = run_config_code(code, config, cwd)
    except Exception as error:  # noqa: BLE001 - report any curator failure
        return None, [*errors, f"config code failed: {error!r}"]
    errors.extend(validation_errors(produced, internal_schema))
    return produced, errors


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


def get_by_path(config, path: list[str], default=None):
    """Resolve a dotted field path in a nested mapping."""
    # TODO: file pattern
    node = config
    for name in path:
        if not isinstance(node, Mapping) or name not in node:
            return default
        node = node[name]
    return node


def read_table(path: Path):
    """Read a table by extension, or ``None`` when unreadable/unsupported."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".tsv":
            return pl.read_csv(path, separator="\t")
        if suffix == ".csv":
            return pl.read_csv(path)
        if suffix == ".xlsx":
            return pl.read_excel(path)
    except Exception:
        pass


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


def _inline_table(data_path: Path | None, value: str):
    schema = None
    example: dict = {}
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


def tables_to_data(tables: Mapping[str, TableSpec]):
    """Convert a table sidecar to plain YAML data (id -> dict)."""
    return yaml.dump(
        {identifier: spec._asdict() for identifier, spec in tables.items()},
        sort_keys=False,
        Dumper=CustomSafeDumper,
    )


def tables_from_data(data: str):
    """Rebuild a table sidecar from plain YAML data (id -> dict)."""
    return {
        str(identifier): TableSpec(**value)
        for identifier, value in (load_yaml(data) or {}).items()
    }


class TableSpec(NamedTuple):
    """A declared table: config field paths, row schema and columnar example.

    The table id is the key of the owning ``dict``; it is not stored here.
    """

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
            value = get_by_path(config, field)
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
                    for message in validation_errors(row, self.schema):
                        errors.append(f"row {index}: {message}")
        return errors


class PreviewResult(NamedTuple):
    """The outcome of running the conversion code in a throw-away directory."""

    errors: list[str]
    files: dict[str, bytes]
    config: dict | None
    examples: dict[str, bytes]

    @property
    def ok(self):
        return not self.errors

    @classmethod
    def run(
        cls,
        code: str,
        config,
        tables: dict[str, TableSpec],
        internal_schema: Mapping | None,
        schema_dir: Path | None,
        *,
        config_target: str = "config/config.yaml",
    ):
        """Run the conversion code over a temp copy of the example tables.

        1. validate the example tables against their own (row) schema, before code,
        2. write the declared example tables and run the code in that directory,
        3. save the returned config,
        4. validate the config against the upstream schema,
        5. validate every produced file against the original repo schema.
        """
        errors: list[str] = []
        for identifier, spec in tables.items():
            errors.extend(
                f"table '{identifier}': {message}" for message in spec.errors()
            )
        if errors:
            return cls(errors, {}, None, {})

        with config_workdir() as cwd:
            for identifier, spec in tables.items():
                table = spec.example_table
                for path in spec.paths(config):
                    try:
                        write_table(table, cwd / path)
                    except Exception as error:  # noqa: BLE001
                        return cls([f"table '{path}': {error!r}"], {}, None, {})
            try:
                produced = run_config_code(code, config, cwd)
            except Exception as error:  # noqa: BLE001 - report any curator failure
                return cls([f"config code failed: {error!r}"], {}, None, {})
            config_file = cwd / config_target
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(yaml.safe_dump(produced, sort_keys=False))
            files = collect_files(cwd)
            examples = {
                path: files[path]
                for spec in tables.values()
                for path in spec.paths(config)
                if path in files
            }

        errors = validation_errors(produced, internal_schema)
        errors += _validate_files(files, schema_dir, skip={config_target})
        return cls(errors=errors, files=files, config=produced, examples=examples)


def _parse_file(name: str, content: bytes):
    suffix = Path(name).suffix.lower()
    if suffix in TABLE_EXTENSIONS:
        buffer = io.BytesIO(content)
        try:
            if suffix == ".tsv":
                return pl.read_csv(buffer, separator="\t")
            if suffix == ".csv":
                return pl.read_csv(buffer)
            return pl.read_excel(buffer)
        except Exception:  # noqa: BLE001 - unparseable files are skipped
            return None
    if suffix in (".json", ".yaml", ".yml"):
        try:
            return load_yaml(content.decode())
        except Exception:  # noqa: BLE001
            return None
    return None


def _find_schema(schema_dir: Path, name: str):
    basename = Path(name).name.split(".")[0]
    for ext in ("yaml", "yml", "json"):
        candidate = schema_dir / f"{basename}.schema.{ext}"
        if candidate.exists():
            return load_yaml(candidate.read_text())
    return None


def _validate_files(files: dict[str, bytes], schema_dir: Path | None, skip: set[str]):
    errors: list[str] = []
    if schema_dir is None:
        return errors
    for name, content in files.items():
        if name in skip:
            continue
        schema = _find_schema(schema_dir, name)
        if schema is None:
            continue
        parsed = _parse_file(name, content)
        if isinstance(parsed, pl.DataFrame):
            for index, row in enumerate(parsed.iter_rows(named=True)):
                for message in validation_errors(row, schema):
                    errors.append(f"{name} row {index}: {message}")
        elif isinstance(parsed, (dict, list)):
            for message in validation_errors(parsed, schema):
                errors.append(f"{name}: {message}")
    return errors
