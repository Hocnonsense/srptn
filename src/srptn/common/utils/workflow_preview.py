"""Running the curator code over a throw-away copy of the tables.

``run_tables`` is the single path used to produce and validate a conversion:
it writes the tables into a temp directory, runs the curator code, then
validates the produced config against the upstream schema and every produced
file against the original repo schema.  It returns ``(files, config)`` and
appends problems to a caller-provided ``errors`` list.  Callers provide ready
tables (``path -> DataFrame``).
"""

from __future__ import annotations

import io

from pathlib import Path
from typing import Mapping

import polars as pl
import yaml

from .config_code import collect_files, config_workdir, run_config_code
from .table_utils import TABLE_EXTENSIONS, read_table, save_data_table
from .schema_validation import validation_errors
from .table_schema import coerce_frame, table_errors
from .yaml_utils import load_yaml, parse_yaml


def run_tables(
    code: str,
    config,
    tables: Mapping[str, pl.DataFrame],
    internal_schema: Mapping | None,
    schema_dir: Path | None,
    errors: list[str],
    *,
    config_target: str = "config/config.yaml",
) -> tuple[dict[str, bytes], dict | None]:
    """Run the conversion code over ready tables (``path -> DataFrame``).

    Returns ``(files, config)``; problems are appended to ``errors`` and, on
    failure, the produced artifacts are ``({}, None)``.
    """
    with config_workdir() as cwd:
        for path, table in tables.items():
            target = cwd / path
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                save_data_table(table, target)
            except pl.exceptions.ComputeError as error:
                # Array columns cannot be written to a flat format; the curator
                # code reads those values through ``read_table`` instead.
                if "nested" not in str(error):
                    errors.append(f"table '{path}': {error!r}")
                    return {}, None
            except Exception as error:  # noqa: BLE001
                errors.append(f"table '{path}': {error!r}")
                return {}, None
        try:
            produced = run_config_code(code, config, cwd, read_table=tables.get)
        except Exception as error:  # noqa: BLE001 - report any curator failure
            errors.append(f"config code failed: {error!r}")
            return {}, None
        config_file = cwd / config_target
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(yaml.safe_dump(produced, sort_keys=False))
        files = collect_files(cwd)

    errors.extend(map(str, validation_errors(produced, internal_schema)))
    errors.extend(_validate_files(files, schema_dir, skip={config_target}))
    return files, produced


def _parse_file(name: str, content: bytes):
    """Parse a produced file into a table/config, or ``None`` when unreadable.

    Tables are read column-wise; any other file is parsed as YAML, which also
    covers ``.json`` (a YAML subset).
    """
    suffix = Path(name).suffix.lower()
    if suffix in TABLE_EXTENSIONS:
        return read_table(io.BytesIO(content), suffix=suffix)
    try:
        parsed, _ = parse_yaml(content.decode())
    except UnicodeDecodeError:  # binary files are skipped
        return None
    return parsed


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
            parsed, _ = coerce_frame(parsed, schema)
            errors.extend(f"{name} {issue}" for issue in table_errors(parsed, schema))
        elif isinstance(parsed, (dict, list)):
            for violation in validation_errors(parsed, schema):
                errors.append(f"{name}: {violation}")
    return errors
