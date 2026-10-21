"""Streamlit host for the TypeScript figure editor."""

from streamlit.components.v2 import component
from streamlit.components.v2.get_bidi_component_manager import (
    get_bidi_component_manager,
)

_COMPONENT_NAME = "srptn.figure_editor"


def _figure_editor():
    manager = get_bidi_component_manager()
    if manager.get_component_asset_root(_COMPONENT_NAME) is None:
        manager.discover_and_register_components()
    return component(
        _COMPONENT_NAME,
        js="index-*.js",
        css="index-*.css",
        isolate_styles=True,
    )


def figure_editor_component(
    *,
    rows: list[dict],
    schema: dict[str, str],
    key: str,
    initial: dict | None = None,
):
    """Render the embedded editor and return its component state.

    The browser receives the selected table through the component's ``data``
    parameter.  The token endpoint and browser cache from the host architecture
    remain a later integration step.
    """
    columns = [{"name": name, "type": vega_type} for name, vega_type in schema.items()]
    return _figure_editor()(
        data={
            "rows": rows,
            "columns": columns,
            "initial": initial,
            "load_token": key,
        },
        key=key,
        default={"value": None},
        on_value_change=lambda: None,
    ).value
