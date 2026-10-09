"""Previewing the config transformation over a throw-away copy of the examples.

``PreviewResult.run`` is the single path used to generate and validate a
curation: it validates the example tables (before the code), runs the code in a
temp directory, then validates the produced config against the upstream schema
and every produced file against the original repo schema.
"""

from __future__ import annotations

import io

from pathlib import Path
from typing import Mapping, NamedTuple

import polars as pl
import yaml

from .config_code import collect_files, config_workdir, run_config_code
from .schema_validation import validation_errors
from .workflow_tables import TABLE_EXTENSIONS, TableSpec, write_table
from .yaml_utils import load_yaml


class PreviewResult(NamedTuple):
    """The outcome of running the conversion code in a throw-away directory."""

    errors: list[str]
    files: dict[str, bytes]
    config: dict | None

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
            return cls(errors, {}, None)

        with config_workdir() as cwd:
            for identifier, spec in tables.items():
                table = spec.example_table
                for path in spec.paths(config):
                    try:
                        write_table(table, cwd / path)
                    except Exception as error:  # noqa: BLE001
                        return cls([f"table '{path}': {error!r}"], {}, None)
            try:
                produced = run_config_code(code, config, cwd)
            except Exception as error:  # noqa: BLE001 - report any curator failure
                return cls([f"config code failed: {error!r}"], {}, None)
            config_file = cwd / config_target
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(yaml.safe_dump(produced, sort_keys=False))
            files = collect_files(cwd)

        errors = validation_errors(produced, internal_schema)
        errors += _validate_files(files, schema_dir, skip={config_target})
        return cls(errors=errors, files=files, config=produced)


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
