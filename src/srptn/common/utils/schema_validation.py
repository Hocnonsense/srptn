"""JSON Schema validation helpers, shared beyond the curation flow.

The project YAML loader keeps scientific-notation floats as strings, so the
``number`` type checker is extended to accept them; the app-specific
``"missing"`` type is dropped before validation.  Table examples are cast to
their declared types before validation (see
:func:`..table_schema.coerce_frame`), so no other leniency is needed.
"""

from __future__ import annotations

from functools import cache
from typing import Generator, Literal, Mapping, overload

import jsonschema.validators
from jsonschema.exceptions import SchemaError, ValidationError
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


@overload
def validation_errors(
    instance, schema: Mapping | None, str: Literal[True]
) -> Generator[str, None, None]: ...
@overload
def validation_errors(
    instance, schema: Mapping | None, str: Literal[False] = False
) -> Generator[ValidationError, None, None]: ...
def validation_errors(instance, schema: Mapping | None, str: bool = False):
    """Return the jsonschema violations of ``instance`` as :class:`Violation`\\ s.

    Callers decide how to present them (``str(violation)`` renders ``path: msg``).
    """
    if not schema:
        return
    schema = sanitize_schema(schema)
    base = jsonschema.validators.validator_for(schema)
    validator = _extended_validator(base)(schema)
    if str:
        for self in validator.iter_errors(instance):
            where = "/".join(f"{part}" for part in self.absolute_path) or "<root>"
            yield f"{where}: {self.message}"
    else:
        yield from validator.iter_errors(instance)


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
