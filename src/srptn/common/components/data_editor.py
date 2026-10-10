import polars as pl
import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit_ace import THEMES, st_ace

from .ui_components import toggle_button
from .table_editor import column_controls, editable_table
from ..data.entities.analysis import WorkflowManager
from ..utils.polars_utils import (
    enforce_typing,
    load_data_table,
    merge_dataframes,
)
from ..utils.schema_inference import infer_schema, update_schema


def clear_data(key: str, frame: pl.DataFrame):
    """Clear all rows of the dataframe.

    :param key: The key for the Streamlit session state.
    :param frame: The current dataframe.
    """
    if st.button(
        "",
        icon=":material/mop:",
        help="Clear all entries",
        key=f"{key}-clear_data_button",
    ):
        return pl.DataFrame(schema=frame.schema), frame


def custom_upload(key: str, frame: pl.DataFrame):
    """Upload a custom configuration file and replace the dataframe.

    :param key: The key for the Streamlit session state.
    :param frame: The current dataframe.
    """
    with st.popover("", icon=":material/upload:", help="Upload a config"):
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=("xlsx", "tsv", "csv"),
            key=f"{key}-custom_upload_field",
        )
        if st.button(
            "Confirm", key=f"{key}-custom_upload_button", disabled=uploaded_file is None
        ):
            assert uploaded_file is not None
            uploaded = load_data_table(uploaded_file, source="upload")
            if isinstance(uploaded, pl.DataFrame):
                return uploaded, uploaded_file.name


def data_editor(key: str):
    """Provide an interface for editing a dataframe with various options.

    :param key: The key for the Streamlit session state.
    """
    holders: list[DeltaGenerator] = st.session_state[f"{key}-placeholders"]
    with holders[0]:
        data, change = column_controls(
            key,
            st.session_state[f"{key}-data"],
            extras=dict(upload=custom_upload, fill=data_fill, clear=clear_data),
        )
    if change:
        st.session_state[f"{key}-data"] = data
    process_user_code(key)
    dataset_ids = list(st.session_state.get("workflow-meta-datasets-sheets", {}))
    with holders[2]:
        editable_table(
            f"{key}-editor",
            st.session_state[f"{key}-data"],
            on_change=update_data,
            args=(key,),
            column_config={
                "datasetid": st.column_config.SelectboxColumn(
                    "datasetid",
                    options=dataset_ids,
                    default=dataset_ids[0] if dataset_ids else None,
                ),
            },
        )
    validate_data(key)
    # FIXME: use a long table with: (id), datasetid, filename, *meta
    # to select sample from it. Define global indexes, use a list of
    # pivot rules to make wide table, and merge them to the final one


def generate_from_to_fields(
    idx: int,
    from_col: str,
    to_col: str,
    key: str,
    data_selected: pl.DataFrame,
):
    """Generate UI for selecting 'From' and 'To' column pairs."""
    cols = st.columns([3, 3, 1])
    with cols[0]:
        st.text("From")
    with cols[1]:
        st.text("To")
    cols = st.columns([3, 3, 1])
    with cols[0]:
        from_col_val = st.selectbox(
            "From",
            options=data_selected.columns,
            index=(
                data_selected.columns.index(from_col)
                if from_col in data_selected.columns
                else 0
            ),
            key=f"{key}-fill_column_select-{idx}",
            label_visibility="collapsed",
        )
    with cols[1]:
        to_col_val = st.text_input(
            "To",
            to_col,
            key=f"{key}-fill_column_alias-{idx}",
            label_visibility="collapsed",
        )
    with cols[2]:
        st.button(
            "",
            key=f"{key}-remove-{idx}",
            on_click=lambda: st.session_state[f"{key}-fill_pairs"].pop(idx),
            icon=":material/remove:",
        )
    return from_col_val, to_col_val


def add_new_from_to_field(key: str, data_selected: pl.DataFrame):
    """Add a new 'From-To' field pair to the session state."""
    next_idx = st.session_state[f"{key}-next_col_idx"] % len(data_selected.columns)
    next_col = data_selected.columns[next_idx]
    st.session_state[f"{key}-fill_pairs"].append((next_col, next_col))
    st.session_state[f"{key}-next_col_idx"] = (next_idx + 1) % len(
        data_selected.columns
    )


def prepare_fill_pairs(key: str, data_selected: pl.DataFrame):
    """Initialize the 'fill_pairs' and related session state variables."""
    if f"{key}-fill_pairs" not in st.session_state:
        default_col = data_selected.columns[0]
        st.session_state[f"{key}-fill_pairs"] = [(default_col, default_col)]
        st.session_state[f"{key}-next_col_idx"] = 1
    return st.session_state[f"{key}-fill_pairs"]


def validate_and_cast_columns(
    data_selected: pl.DataFrame,
    data_modified: pl.DataFrame,
    from_col: str,
    to_col: str,
):
    """Validate and cast columns as necessary."""
    column_to_add = data_selected.select(pl.col(from_col).alias(to_col))
    if to_col in data_modified.columns:
        if data_modified.schema[to_col] != column_to_add.schema[to_col]:
            st.warning(f"Column '{to_col}' has a different type")
            try:
                column_to_add = column_to_add.cast(data_modified.schema[to_col])
            except pl.exceptions.InvalidOperationError:
                st.error(
                    f"Failed to cast column '{from_col}' to match the existing '{to_col}' type",
                )
                st.stop()
    return column_to_add


def data_fill(key: str, frame: pl.DataFrame):
    """Fill the configuration file with data from a selected dataset."""
    with st.popover("", icon=":material/library_add:"):
        dataset = st.session_state.get("workflow-meta-datasets-sheets")
        if not dataset:
            return
        selected = st.selectbox(
            "Select a dataset",
            options=list(dataset),
            key=f"{key}-fill_data_select",
        )
        if selected:
            data_selected = dataset[selected]
            data_modified: pl.DataFrame = frame.clone()

            fill_pairs = prepare_fill_pairs(key, data_selected)

            for i, (from_col, to_col) in enumerate(fill_pairs):
                fill_pairs[i] = generate_from_to_fields(
                    i,
                    from_col,
                    to_col,
                    key,
                    data_selected,
                )

            st.button(
                "",
                key=f"{key}-add_next",
                on_click=lambda: add_new_from_to_field(key, data_selected),
                icon=":material/add:",
            )

            columns_to_add: list[pl.DataFrame] = []
            for from_col, to_col in fill_pairs:
                column_to_add = validate_and_cast_columns(
                    data_selected,
                    data_modified,
                    from_col,
                    to_col,
                )
                columns_to_add.append(column_to_add)

            if columns_to_add:
                data_modified = merge_dataframes(
                    data_modified,
                    columns_to_add,
                    selected,
                )

            st.dataframe(
                data_modified,
                height=250,
                use_container_width=True,
                key=f"{key}-fill_preview_window",
            )

            if st.button("Confirm", key=f"{key}-fill_button"):
                return data_modified, [pair[1] for pair in fill_pairs]


def data_selector(
    label: str,
    value: str,
    key: str,
    workflow_manager: WorkflowManager,
):
    """Create a data selector widget in Streamlit.

    :param label: The label for the text input widget.
    :param value: The initial value of the text input.
    :param key: The key to store the text input value in Streamlit's session state.
    :param workflow_manager: An object providing data-related functions.
    :return: A tuple containing the input value and a boolean indicating whether to show the data editor.
    """
    st.text(label)
    col1, col2 = st.columns([9, 1])
    with col1:
        input_value = st.text_input(
            label=label,
            value=value,
            key=key,
            disabled=True,
            label_visibility="collapsed",
        )
    data_key = f"{key}-data"
    data_key_changed = f"{key}-data_token"
    data_schema_key = f"{key}-schema"

    if (
        data_key not in st.session_state
        or data_key_changed not in st.session_state
        or st.session_state[data_key_changed] != input_value
    ):
        if data_schema_key in st.session_state:
            st.session_state.pop(data_schema_key)

        st.session_state[data_key] = load_data_table(
            workflow_manager.workspace.data_path / input_value,
        )

        st.session_state[data_key_changed] = input_value

    if not isinstance(st.session_state[data_key], pl.DataFrame):
        # st.error reported in load_data_table
        return input_value, False
    st.session_state[data_key] = st.session_state[data_key].with_columns(
        datasetid=pl.lit(""),
    )

    if data_schema_key not in st.session_state:
        data_schema = workflow_manager.get_schema(value.split("/")[-1].split(".")[0])
        data_config = st.session_state[data_key].to_dict(as_series=False)
        if data_schema:
            final_schema = update_schema(data_schema, data_config)
        else:
            final_schema = infer_schema(data_config)
        st.session_state[data_schema_key] = final_schema
        st.session_state[data_key] = enforce_typing(
            st.session_state[data_key],
            final_schema,
        )

    with col2:
        show_data: bool = toggle_button("", key, icon=":material/keyboard_arrow_down:")
    return input_value, show_data


def execute_custom_code(
    data,
    key: str,
    user_code: str,
):
    """Execute custom code provided by the user on the dataframe.

    :param data: The dataframe on which the custom code will be executed.
    :param user_code: The custom code to execute on the dataframe.
    :param mode: The mode to determine whether the result should be applied or returned.
    :return: The dataframe after the custom code has been executed, or None if mode is 'apply'.
    """
    if not isinstance(data, pl.DataFrame):
        st.error("The provided data is not a Polars DataFrame.")
        return
    user_code = "import polars as pl\nimport numpy as np\n" + user_code
    local_vars = {}
    for k, value in [
        (k, value)
        for k, value in st.session_state.items()
        if (
            isinstance(k, str)
            and k.startswith("workflow-config-")
            and k.endswith("-data")
            and isinstance(value, pl.DataFrame)
            and f"{key}-data" != k
        )
    ]:
        local_var_key = k[16:-5].split(".")[-1]
        local_vars[local_var_key] = value

    local_vars["df"] = data
    exec(user_code, {}, local_vars)
    data = local_vars.get("df", data)
    if not isinstance(data, pl.DataFrame):
        st.error("The returned object is not a Polars DataFrame.")
    else:
        return data


def modify_schema(schema: dict, key: str):
    """Rename a column in the dataframe schema.

    :param schema: The data schema.
    :param key: The key for the Streamlit session state.
    :return: The data schema with the renamed column.
    """
    with st.popover("Modify"):
        selected = st.selectbox(
            "Select column-schema to rename",
            options=schema["properties"].keys(),
            key=f"{key}-modify_column_select",
        )
        renamed = st.text_input(
            "Rename to",
            value=selected,
            key=f"{key}-modify_column_text",
        )
        rename = st.button("Rename", key=f"{key}-modify_column_button")
        if rename and (renamed or "").strip():
            schema["properties"][renamed] = schema["properties"].pop(selected)
            if selected in schema["required"]:
                schema["required"] = [
                    x.replace(selected, renamed) for x in schema["required"]
                ]
    return schema


def process_user_code(key: str):
    """Modify the dataframe using user-provided Python code.

    :param key: The key for the Streamlit session state that identifies the data.
    """
    with st.session_state[f"{key}-placeholders"][1].expander(
        "Advanced table modification",
        expanded=True,
    ):
        acestring = (
            "# The table is available as df: pl.DataFrame\n"
            "# All other tables are accessible through their file name\n"
        )

        c1, c2 = st.columns([3.25, 1])
        with c1:
            user_code = st_ace(
                acestring,
                auto_update=False,
                language="python",
                height=300,
                theme=c2.selectbox(
                    "Theme",
                    options=THEMES,
                    index=35,
                    key=f"{key}-color_theme",
                ),
                font_size=c2.slider(
                    "Font size",
                    5,
                    24,
                    14,
                    key=f"{key}-font_size_slider",
                ),
                key=f"{key}-st_ace",
            )
        no_import = True
        if "import " in user_code:
            for line in user_code.splitlines():
                if line.strip().startswith("import "):
                    no_import = False
                    st.error("Remove line with 'import' as no imports are allowed.")
                    break
        col1, col2 = c2.columns(2)
        with col1:
            preview = st.button(
                "",
                key=f"{key}-advanced_manipulation_preview_config",
                disabled=not no_import,
                icon=":material/pageview:",
                help="Preview the changes",
            )
        with col2:

            def set_refresh(key, user_code):
                st.session_state[f"{key}-data"] = execute_custom_code(
                    st.session_state[f"{key}-data"],
                    key,
                    user_code,
                )

            st.button(
                "",
                key=f"{key}-advanced_manipulation_apply_config",
                disabled=not no_import,
                icon=":material/publish:",
                help="Apply the changes",
                on_click=set_refresh,
                args=(
                    key,
                    user_code,
                ),
            )
        if preview:
            preview_data = st.session_state[f"{key}-data"].clone()
            # returned again as preview_data does not need to be placed in session state
            preview_data = execute_custom_code(preview_data, key, user_code)
            st.dataframe(
                preview_data,
                use_container_width=True,
                key=f"{key}-advanced_manipulation_preview_window",
            )
            validate_data(key, preview_data)


def update_data(key: str):
    """Update the data in the session state based on user edits.

    :param key: The key for the Streamlit session state that identifies the data.
    """
    editor = st.session_state[f"{key}-editor"]["edited_rows"]
    data = st.session_state[f"{key}-data"]
    if editor:
        for idx, row_edits in editor.items():
            for colname, new_value in row_edits.items():
                data[idx, colname] = new_value
        st.session_state[f"{key}-data"] = data
    else:
        st.warning("No edits detected in the data editor.")


def validate_data(key: str, data: pl.DataFrame | None = None):
    """Validate a dataset against its associated schema.

    :param key: The key for the Streamlit session state identifying the dataset and schema.
    :param data: The dataset to be validated. If not provided, it will be fetched from the Streamlit session state.
    """

    # Fetch data and schema if not provided
    if data is None:
        data = st.session_state.get(f"{key}-data")
        if data is None:
            st.error(f"No data found for key: {key}")
            return

    data_dict = data.to_dict(as_series=False)
    schema = st.session_state.get(f"{key}-schema")
    if not schema:
        st.error(f"No schema found for key: {key}")
        return

    required_fields = schema.get("required", [])
    properties = schema.get("properties", {})

    st.session_state["workflow-config-form-valid"][key] = True
    for field, field_info in properties.items():
        column_data = data_dict.get(field)
        is_required = field in required_fields
        if is_required and not column_data:
            report_missing_required_field(key, field)
            continue

        if column_data:
            validate_column_data(
                key,
                field,
                column_data,
                field_info,
                is_required=is_required,
            )


def report_missing_required_field(key: str, field: str):
    """Report a missing required field.

    :param key: The key for the Streamlit session state identifying the dataset.
    :param field: The missing field name.
    """
    st.session_state["workflow-config-form-valid"][key] = False
    st.error(f'Column "{field}" is required but not found.')


def validate_column_data(
    key: str,
    field: str,
    column_data: list,
    field_info: dict,
    *,
    is_required: bool,
):
    """Validate a single column against its schema definition.

    :param key: The key for the Streamlit session state identifying the dataset.
    :param field: The name of the column being validated.
    :param column_data: The data of the column as a list.
    :param field_info: Schema definition for the field, including type constraints.
    :param is_required: Whether the field is marked as required.
    """

    def is_value_valid(value, expected_type: str):
        match expected_type:
            case "boolean":
                return str(value).lower() in {"true", "false", "0", "1"}
            case "string":
                return bool(str(value).strip())
            case "number":
                return isinstance(value, int | float)
            case _:
                return True

    invalid_rows = []

    for idx, value in enumerate(column_data):
        if not is_value_valid(value, field_info["type"]):
            invalid_rows.append(idx + 1)

    if invalid_rows:
        row_string = (
            "s " + ", ".join(map(str, invalid_rows))
            if len(invalid_rows) > 1
            else f" {invalid_rows[0]}"
        )
        message = (
            f'Column "{field}" expects a "{field_info["type"]}" on row{row_string}.'
        )

        if is_required:
            st.session_state["workflow-config-form-valid"][key] = False
            st.error(message)
        else:
            st.warning(message)
