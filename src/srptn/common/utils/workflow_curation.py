"""Pure helpers for the workflow curation (publisher) flow.

These functions carry the testable logic behind the publisher page: wrapping
the maintainer's Python body into ``parse_config``, rewriting the generated
wrapper ``Snakefile`` to use it, sanitizing an app-inferred schema into valid
JSON Schema, and validating a produced config against the upstream schema.
"""

from __future__ import annotations

import re
import textwrap

from typing import Any, Mapping, overload

import jsonschema.validators
import yaml

from .yaml_utils import CustomSafeLoader

PARSE_CONFIG_IMPORT = 'include: "parse_config.py"'
PARSE_CONFIG_UPDATE = "config = parse_config(config)"
DEFAULT_BODY = "return config"


def load_yaml(text: str):
    """Parse YAML using the project loader (keeps scientific floats as strings)."""
    return yaml.load(text, Loader=CustomSafeLoader)


def wrap_parse_config(body: str):
    """Wrap a maintainer-provided body into ``def parse_config(config): ...``."""
    body = textwrap.dedent(body or DEFAULT_BODY).strip("\n")
    return f"def parse_config(config):\n{textwrap.indent(body, '    ')}\n"


def rewrite_snakefile(source: str):
    """Idempotently insert the parse_config include and config update.

    The lines are placed right after ``configfile:`` when present, otherwise
    before the ``module`` block; if neither is found they go at the end.
    """
    if PARSE_CONFIG_IMPORT in source or PARSE_CONFIG_UPDATE in source:
        return source
    lines = source.splitlines()
    index = len(lines)
    for i, line in enumerate(lines):
        if line.startswith("configfile:"):
            index = i + 1
            break
    else:
        for i, line in enumerate(lines):
            if line.startswith("module"):
                index = i
                break
    lines[index:index] = [PARSE_CONFIG_IMPORT, PARSE_CONFIG_UPDATE]
    result = "\n".join(lines)
    return result + "\n" if source.endswith("\n") else result


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


def validation_errors(instance: Any, schema: Mapping | None) -> list[str]:
    """Return all jsonschema violations as ``"path: message"`` strings."""
    if not schema:
        return []
    validator_class = jsonschema.validators.validator_for(schema)
    validator = validator_class(schema)
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
        f"{error.message}"
        for error in errors
    ]


def compile_parse_config(source: str):
    """Execute wrapped source and return the ``parse_config`` callable."""
    namespace: dict[str, Any] = {}
    exec(source, namespace)  # noqa: S102 - deliberate execution of curator code
    return namespace["parse_config"]


def transform_errors(
    body: str,
    config: Any,
    external_schema: Mapping | None,
    internal_schema: Mapping | None,
):
    """Run the curator transform and validate its output.

    Returns the produced config and the combined errors: the external config
    against the external schema, and the transform output against the upstream
    internal schema.
    """
    errors = validation_errors(config, sanitize_schema(external_schema))
    try:
        produced = compile_parse_config(wrap_parse_config(body))(config)
    except Exception as error:  # noqa: BLE001 - report any curator failure
        return None, [*errors, f"parse_config failed: {error!r}"]
    errors.extend(validation_errors(produced, sanitize_schema(internal_schema)))
    return produced, errors


def snakefile_module_name(name: str) -> str:
    """Sanitize a workflow name into a valid Snakemake module identifier."""
    sanitized = re.sub(r"[^0-9A-Za-z_]", "_", name or "").strip("_")
    return sanitized or "workflow"
