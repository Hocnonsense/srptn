"""JSON Schema validation helpers, shared beyond the curation flow.

The project YAML loader keeps scientific-notation floats as strings, so the
``number`` type checker is extended to accept them; the app-specific
``"missing"`` type is dropped before validation.  Table examples are cast to
their declared types before validation (see
:func:`..workflow_tables.coerce_frame`), so no other leniency is needed.
"""

from __future__ import annotations

from functools import cache
from typing import Mapping, overload

import jsonschema.validators
from jsonschema.exceptions import SchemaError
from jsonschema.protocols import Validator

from .yaml_utils import SCIENTIFIC_FLOAT


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
def _extended_validator(base: type[Validator]) -> type[Validator]:
    def _is_number(type_checker, value):
        if isinstance(value, str):
            return bool(SCIENTIFIC_FLOAT.match(value))
        return not isinstance(value, bool) and isinstance(value, (int, float))

    return jsonschema.validators.extend(
        base, type_checker=base.TYPE_CHECKER.redefine("number", _is_number)
    )


def validation_errors(instance, schema: Mapping | None):
    """Return all jsonschema violations as ``"path: message"`` strings."""
    if schema:
        schema = sanitize_schema(schema)
        base = jsonschema.validators.validator_for(schema)
        validator = _extended_validator(base)(schema)
        errors = sorted(
            validator.iter_errors(instance),
            key=lambda error: list(error.absolute_path),
        )
    else:
        errors = []
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
        f"{error.message}"
        for error in errors
    ]


def schema_errors(schema: Mapping | None):
    """Return meta-schema violations of ``schema`` as strings, ``[]`` if valid.

    A malformed schema (for example a ``required`` list placed inside
    ``properties``) makes jsonschema silently ignore that branch, so nested
    content goes unvalidated; checking the schema itself surfaces the mistake.
    """
    if not schema:
        return []
    schema = sanitize_schema(schema)
    validator = jsonschema.validators.validator_for(schema)
    try:
        validator.check_schema(schema)
    except SchemaError as error:
        return [error.message]
    return []
