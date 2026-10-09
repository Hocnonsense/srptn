import re

import streamlit as st
import yaml
from polars import DataFrame
from streamlit_ace import st_ace
from streamlit_tags import st_tags

from .data_editor import data_editor, data_selector
from .schemas import get_property_type
from ..data.entities.analysis import WorkflowManager
from ..utils.yaml_utils import load_yaml, dump_yaml


def ace_config_editor(
    config: dict,
    final_schema: dict,
    workflow_manager: WorkflowManager,
):
    """Edit a configuration file using the ACE editor in the Streamlit app.

    :param config: The configuration dictionary to be edited.
    :param final_schema: The schema that defines the structure and types of the config.
    :param workflow_manager: An object providing data-related functions.
    """
    value = st_ace(dump_yaml(config), language="yaml")
    try:
        parsed_config = None if value is None else load_yaml(value)
    except yaml.YAMLError as error:
        st.error(f"Error parsing config YAML: {error}")
        return
    if parsed_config is None:
        parsed_config = {}
    if not isinstance(parsed_config, dict):
        st.error("Workflow configuration must be a YAML mapping.")
        return
    create_form(
        parsed_config,
        final_schema,
        workflow_manager,
        "workflow-config-",
        ace_editor=True,
    )


def config_editor(
    config: dict,
    final_schema: dict,
    workflow_manager: WorkflowManager,
):
    """Edit a configuration file in the Streamlit app using input elements.

    :param config: The configuration dictionary to be edited.
    :param final_schema: The schema that defines the structure and types of the config.
    :param workflow_manager: An object providing data-related functions.
    """
    create_form(config, final_schema, workflow_manager, "workflow-config-")


def create_form(
    config: dict,
    schema: dict,
    workflow_manager: WorkflowManager,
    parent_key: str = "",
    *,
    ace_editor: bool = False,
):
    """Generate a dynamic Streamlit form based on a config dictionary and schema.

    :param config: The configuration dictionary to populate the form.
    :param schema: The schema defining the structure and validation rules for the config.
    :param workflow_manager: An object providing data-related functions.
    :param parent_key: A key used to track nested configuration items, defaults to "".
    :param ace_editor: Whether the form is used with the ACE editor, defaults to False.
    """
    prop_key = get_property_type(schema)
    required_fields = schema.get("required", [])
    new_tabs = []
    for key, value in config.items():
        if not isinstance(value, dict):  # check for leaf nodes = endpoints
            unique_element_id = update_key(parent_key, key)
            input_dict = schema[prop_key].get(key)
            if not input_dict:
                continue
            only_validation = ace_editor and not (
                input_dict["type"] == "string"
                and value
                and value.endswith((".tsv", ".csv", ".xlsx"))
            )
            # input_element is self-contained and returns to config in session-state
            get_input_element(
                key,
                value,
                input_dict,
                unique_element_id,
                workflow_manager,
                required=key in required_fields,
                ace_editor=only_validation,
            )
        else:
            new_tabs.append((key, value))

    if new_tabs:
        if not ace_editor:
            tabs = st.tabs([key for key, _ in new_tabs])
        for tab, (key, value) in enumerate(new_tabs):
            updated_parent_key = update_key(parent_key, key)
            if prop_key == "patternProperties":
                if not re.search(next(iter(schema[prop_key])), key):
                    st.error("Field name does not match schema.")
                updated_key = next(iter(schema[prop_key]))
            else:
                updated_key = key
            if not ace_editor:
                with tabs[tab]:
                    new_schema = schema[prop_key].get(updated_key)
                    create_form(value, new_schema, workflow_manager, updated_parent_key)
            else:
                new_schema = schema[prop_key].get(updated_key)
                create_form(
                    value,
                    new_schema,
                    workflow_manager,
                    updated_parent_key,
                    ace_editor=True,
                )


def handle_array_input(label: str, value, key: str):
    """Handle input for array types."""
    # cannot differentiate type here ~ no way to represent array of ints or floats except stringified
    if not isinstance(value, list):
        value = [value]
    return st_tags(label=label, value=value, key=key)


def handle_string_input(
    label: str,
    value: str,
    key: str,
    workflow_manager: WorkflowManager,
):
    """Handle input for string types."""
    if not value.endswith((".tsv", ".csv", ".xlsx")):
        return st.text_input(label=label, value=value, key=key)
    input_value, show_data = data_selector(label, value, key, workflow_manager)
    # workaround for popver and expander "bug"
    st.session_state[f"{key}-placeholders"] = [st.empty() for _ in range(3)]
    if show_data and isinstance(st.session_state[f"{key}-data"], DataFrame):
        data_editor(key)
    return input_value


def handle_number_input(label: str, value, key: str):
    """Handle input for numeric types."""
    if "e" in str(value).lower():
        tag = "scn"
        value = value[:-3] if value.endswith(tag) else value
        return st.text_input(label=label, value=value, key=key), tag
    step = 10 ** -len(str(value).split(".")[-1]) if "." in str(value) else 0
    return (
        st.number_input(
            label=label,
            value=value,
            key=key,
            step=step,
        ),
        "",
    )


def update_config_value(input_key: str, tag: str):
    """Update the configuration value in the session state.

    :param input_key: The key for the input element.
    :param tag: A tag to append to the value.
    """
    config = st.session_state["workflow-config-form"]
    new_value = st.session_state[input_key]
    if tag:
        new_value += tag
    keys = input_key.split("-", 2)[-1].split(".")[1:]
    cur = config
    for key in keys[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            st.error(f"Config path {'/'.join(keys)} is invalid")
            return
        cur = nxt
    cur[keys[-1]] = new_value


def validate_and_report(
    input_value,
    input_type: list | str,
    key: str,
    *,
    required: bool,
):
    """Validate the input value and report issues if necessary.

    :param input_value: The value to validate.
    :param input_type: The type of input.
    :param key: The key for the input element.
    :param required: Whether the input is required.
    """
    if required:
        valid = validate_input(input_value, input_type)
        # data inputs are validated in the data_editor and must not be overwritten here
        if key not in st.session_state["workflow-config-form-valid"]:
            st.session_state["workflow-config-form-valid"][key] = valid
        if not valid:
            report_invalid_input(input_value, key, input_type)


@st.fragment
def get_input_element(
    label: str,
    value,
    input_dict: dict,
    key: str,
    workflow_manager: WorkflowManager,
    *,
    required: bool,
    ace_editor: bool,
):
    """Generate a Streamlit input element and validate its value.

    :param label: The label for the input element.
    :param value: The current value of the input element.
    :param input_dict: Schema details for the input element.
    :param key: A unique key identifying the input element.
    :param workflow_manager: An object providing data-related functions.
    :param required: Whether the input is mandatory.
    :param ace_editor: Whether the input element is part of an ACE editor form.
    """
    input_type = input_dict.get("type", "missing")
    input_value = value
    tag = ""
    if not ace_editor:  # Do not show in ace_editor just validate
        if "array" in input_type or (
            isinstance(input_type, list) and isinstance(value, list)
        ):
            input_value = handle_array_input(label, value, key)
        elif isinstance(input_type, list) and not isinstance(value, list):
            # input has multiple types and value is not a list => text_input can handle all remaining types
            input_value = handle_string_input(label, str(value), key, workflow_manager)
        elif input_type == "string":
            input_value = handle_string_input(label, str(value), key, workflow_manager)
        elif input_type in ("integer", "number"):
            input_value, tag = handle_number_input(label, value, key)
        elif input_type == "boolean":
            input_value = st.checkbox(label=label, value=bool(value), key=key)
        elif input_type == "missing":
            # empty endpoints default to list
            input_value = st_tags(label=label, value=value, key=key)
        else:
            st.error("No fitting input was found for your data!")
        # Needs to be updated this way as we never want to have the page rerun but still update the config for deposition
        # Cannot be bound to on_change as st_tags does not support it
        update_config_value(key, tag)
    validate_and_report(input_value, input_type, key, required=required)


def report_invalid_input(value, key: str, input_type: str | list):
    """Display an error message for invalid input values in the Streamlit app.

    :param value: The current value of the input element.
    :param key: The key associated with the invalid input.
    :param input_type: The expected type of the input.
    """
    msg = ">".join(key.split(".")[1:])
    if input_type == "string" and not str(value).strip():
        st.error(f"{msg} must not be empty")
    else:
        st.error(f"{msg} is filled incorrectly")


def update_key(parent_key: str, new_key: str):
    """Append a new key to an existing parent key, forming a dot-separated string.

    :param parent_key: The existing key string.
    :param new_key: The new key to append.
    :return: The concatenated key string.
    """
    return f"{parent_key}.{new_key}" if parent_key != "" else new_key


def validate_input(value, input_type: str | list):
    """Validate a value based on its expected input type.

    :param value: The value to validate.
    :param input_type: The expected type of the value.
    :return: True if the value is valid, False otherwise.
    """
    if input_type == "boolean":
        return True
    if input_type == "string":
        # no isinstance as the value might be an int or float as string
        if not str(value).strip() or not value:
            return False
    if input_type == "number":
        if "e" in str(value).lower():
            return True
        if not isinstance(value, int | float):
            return False
    return True
