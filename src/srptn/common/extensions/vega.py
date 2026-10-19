"""Schema-constrained Vega-Lite definitions for the G0 figure editor.

Only the chart types and encodings in the first vertical slice are modelled:
point, bar and line marks with x/y/color/size encodings, a small set of
filters, and title/axis labels.  The spec binds its data through a named
dataset (``data``); a renderer or generated rule is responsible for injecting
the actual rows.  Nothing here reads data, renders a chart, or runs code.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import dataclass
from typing import Mapping

from ..utils.issues import Issue

SCHEMA_URL = "https://vega.github.io/schema/vega-lite/v5.json"
DATA_NAME = "data"
CHART_TYPES = ("point", "bar", "line")
AGGREGATES = ("none", "count", "mean", "median", "sum", "min", "max")
VEGA_TYPES = ("quantitative", "nominal", "ordinal", "temporal")
FILTER_OPS = ("==", "!=", "<", "<=", ">", ">=", "in")

_NUMERIC_OPS = ("<", "<=", ">", ">=")

_PREDICATE_KEYS = {
    "==": "equal",
    "<": "lt",
    "<=": "lte",
    ">": "gt",
    ">=": "gte",
}


@dataclass(frozen=True)
class Filter:
    """One filter applied before encoding."""

    column: str
    op: str
    value: str = ""


@dataclass(frozen=True)
class FigureConfig:
    """The declarative chart configuration edited in the UI.

    ``columns`` are not stored here: they are supplied as a separate schema
    snapshot so the same configuration can be checked against new data later.
    """

    chart: str = "point"
    x: str | None = None
    y: str | None = None
    color: str | None = None
    size: str | None = None
    aggregate: str = "none"
    filters: tuple[Filter, ...] = ()
    title: str = ""
    x_title: str = ""
    y_title: str = ""

    def to_dict(self) -> dict:
        """Return a JSON/YAML-friendly representation."""
        return {
            "chart": self.chart,
            "x": self.x,
            "y": self.y,
            "color": self.color,
            "size": self.size,
            "aggregate": self.aggregate,
            "filters": [
                {"column": item.column, "op": item.op, "value": item.value}
                for item in self.filters
            ],
            "title": self.title,
            "x_title": self.x_title,
            "y_title": self.y_title,
        }

    @classmethod
    def from_dict(cls, data: Mapping):
        """Rebuild a configuration produced by :meth:`to_dict`."""
        return cls(
            chart=data.get("chart", "point"),
            x=data.get("x"),
            y=data.get("y"),
            color=data.get("color"),
            size=data.get("size"),
            aggregate=data.get("aggregate", "none"),
            filters=tuple(
                Filter(
                    column=item["column"],
                    op=item["op"],
                    value=item.get("value", ""),
                )
                for item in data.get("filters", ())
            ),
            title=data.get("title", ""),
            x_title=data.get("x_title", ""),
            y_title=data.get("y_title", ""),
        )


def validate(config: FigureConfig, columns: Mapping[str, str]) -> list[Issue]:
    """Return the problems that prevent ``config`` from becoming a spec."""
    issues: list[Issue] = []

    def check_column(name: str | None, field: str, optional: bool = False):
        if not name:
            if not optional:
                issues.append(Issue(f"Choose a {field} column.", column=field))
            return
        if name not in columns:
            issues.append(Issue(f"Column '{name}' does not exist.", column=field))
        elif columns[name] not in VEGA_TYPES:
            issues.append(
                Issue(
                    f"Column '{name}' has unsupported type '{columns[name]}'.",
                    column=field,
                )
            )

    if config.chart not in CHART_TYPES:
        issues.append(Issue(f"Unsupported chart type '{config.chart}'."))
    if config.aggregate not in AGGREGATES:
        issues.append(Issue(f"Unsupported aggregate '{config.aggregate}'."))

    check_column(config.x, "x")
    check_column(config.color, "color", optional=True)
    check_column(config.size, "size", optional=True)

    if config.aggregate == "count":
        if config.chart not in ("bar", "point"):
            issues.append(
                Issue("Count aggregation is only available for point and bar charts.")
            )
    else:
        check_column(config.y, "y")
        if config.y and config.y in columns:
            y_type = columns[config.y]
            if config.aggregate != "none" and y_type != "quantitative":
                issues.append(
                    Issue(
                        f"Aggregating '{config.y}' requires a quantitative column.",
                        column="y",
                    )
                )
            if config.chart == "bar" and y_type != "quantitative":
                issues.append(
                    Issue(
                        f"A bar chart requires a quantitative y column; '{config.y}' is {y_type}.",
                        column="y",
                    )
                )
            if (
                config.chart in ("point", "line")
                and config.aggregate == "none"
                and y_type not in ("quantitative", "temporal")
            ):
                issues.append(
                    Issue(
                        f"'{config.y}' must be quantitative or temporal for a {config.chart} chart.",
                        column="y",
                    )
                )

    if config.size and config.size in columns:
        if columns[config.size] not in ("quantitative", "ordinal", "nominal"):
            issues.append(
                Issue(
                    "Size encoding requires a quantitative, ordinal or nominal column.",
                    column="size",
                )
            )

    for index, item in enumerate(config.filters):
        if not item.column:
            issues.append(Issue("Choose a filter column.", row=index))
            continue
        if item.column not in columns:
            issues.append(
                Issue(
                    f"Filter column '{item.column}' does not exist.",
                    row=index,
                    column="filter",
                )
            )
            continue
        if item.op not in FILTER_OPS:
            issues.append(
                Issue(
                    f"Unsupported filter operator '{item.op}'.",
                    row=index,
                    column="filter",
                )
            )
            continue
        if item.op in _NUMERIC_OPS and columns[item.column] != "quantitative":
            issues.append(
                Issue(
                    f"Filter '{item.op}' requires a quantitative column.",
                    row=index,
                    column="filter",
                )
            )
            continue
        if _parse_value(item, columns[item.column]) is None:
            issues.append(
                Issue(
                    f"Filter value '{item.value}' is not valid for {columns[item.column]} "
                    f"column '{item.column}'.",
                    row=index,
                    column="filter",
                )
            )

    return issues


def build_spec(
    config: FigureConfig, columns: Mapping[str, str]
) -> tuple[dict | None, list[Issue]]:
    """Build the Vega-Lite spec, or return the validation issues."""
    issues = validate(config, columns)
    if issues:
        return None, issues

    assert config.x is not None
    encoding = {"x": _field(config.x, columns[config.x], config.x_title)}

    if config.aggregate == "count":
        encoding["y"] = {
            "aggregate": "count",
            "type": "quantitative",
            "title": config.y_title or "Count",
        }
    else:
        assert config.y is not None
        y = _field(config.y, columns[config.y], config.y_title)
        if config.aggregate != "none":
            y["aggregate"] = config.aggregate
        encoding["y"] = y

    if config.color:
        encoding["color"] = _field(config.color, columns[config.color])
    if config.size:
        encoding["size"] = _field(config.size, columns[config.size])

    spec = {
        "$schema": SCHEMA_URL,
        "data": {"name": DATA_NAME},
        "mark": {"type": config.chart, "tooltip": True},
        "encoding": encoding,
    }
    if config.title:
        spec["title"] = config.title
    if config.filters:
        spec["transform"] = [
            {"filter": _predicate(item, columns[item.column])}
            for item in config.filters
        ]
    return spec, []


def definition(
    config: FigureConfig,
    columns: Mapping[str, str],
    *,
    input_binding: Mapping | None = None,
) -> tuple[dict | None, list[Issue]]:
    """Return a serializable definition with a stable content digest.

    The digest covers the input binding, schema snapshot, configuration and
    generated spec. It identifies this definition revision; the binding's
    ``content_digest`` separately identifies the table bytes that were shown.
    """
    spec, issues = build_spec(config, columns)
    if issues:
        return None, issues
    payload = {
        "schema_version": 1,
        "kind": "vega_lite",
        "columns": dict(columns),
        "config": config.to_dict(),
        "spec": spec,
    }
    if input_binding is not None:
        payload["input"] = dict(input_binding)
    payload["content_digest"] = content_digest(payload)
    return payload, []


def content_digest(payload) -> str:
    """Return a canonical SHA-256 digest for a JSON-serializable payload."""
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _field(name: str, vega_type: str, title: str = "") -> dict:
    field = {"field": name, "type": vega_type}
    if title:
        field["title"] = title
    return field


def _parse_value(item: Filter, vega_type: str):
    """Coerce a widget string to the type Vega-Lite compares against."""
    if item.op == "in":
        values = [part.strip() for part in item.value.split(",")]
        if not any(values):
            return None
        return [_parse_scalar(value, vega_type) for value in values if value]
    return _parse_scalar(item.value, vega_type)


def _parse_scalar(value: str, vega_type: str):
    value = value.strip()
    if vega_type == "quantitative":
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
    if vega_type == "temporal":
        return value or None
    return value


def _predicate(item: Filter, vega_type: str) -> dict:
    if item.op == "in":
        return {"field": item.column, "oneOf": _parse_value(item, vega_type)}
    value = _parse_value(item, vega_type)
    if item.op == "!=":
        return {"not": {"field": item.column, "equal": value}}
    return {"field": item.column, _PREDICATE_KEYS[item.op]: value}
