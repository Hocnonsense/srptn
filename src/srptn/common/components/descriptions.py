import streamlit as st

from .ui_components import persistent_text_area


def desc_editor(key: str):
    """Edit and preview a text description in Markdown format.

    :param key: A string prefix to uniquely identify session state keys for descriptions.
    :return: The text entered in the description area as a string.
    """
    if st.button("Edit description", f"{key}-description-open"):
        persistent_text_area(
            "",
            f"{key}-description",
            "Enter description",
            "Markdown Format",
        )
    desc = st.session_state.get(f"{key}-description", "")
    if desc:
        st.caption("Preview")
        st.markdown(desc)
    return desc
