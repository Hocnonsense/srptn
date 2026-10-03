import re

import streamlit as st


def category_editor(key: str):
    """Create and manages a category editor interface using Streamlit.

    :param key: A string prefix to uniquely identify session state keys for categories.
    :returns: A list of category and subcategory inputs, excluding the placeholder for
    new entries.
    """

    def update_categories(position: int):
        st.session_state[f"{key}-categories"][position] = st.session_state[
            f"{key}-category-{position}"
        ]
        st.session_state[f"{key}-categories"] = [
            cat for cat in st.session_state[f"{key}-categories"] if cat
        ] + [""]

    # FIXME: use st.session_state[f"{key}-categories"] = {position: cat}
    # and st.session_state[f"{key}-category-next-position"] += 1 to avoid position shift
    if f"{key}-categories" not in st.session_state:
        st.session_state[f"{key}-categories"] = [""]

    categories = [
        st.text_input(
            "Category" if not position else "Subcategory",
            value=cat,
            key=f"{key}-category-{position}",
            on_change=update_categories,
            args=(position,),
            placeholder="Enter category/subcategory",
        )
        or ""
        for position, cat in enumerate(st.session_state[f"{key}-categories"])
    ]
    check_path(categories)
    return categories[:-1]


def check_path(categories: list[str]):
    if any(cat.startswith("/") for cat in categories):
        st.error("Categories cannot start with slashes")
        st.stop()
    if {".", ".."} & set("/".join(categories).split("/")):
        st.error("Invalid '.' and '..' used in category")
        # TODO: put such user in the black list for warning
        st.stop()


if __name__ == "__main__":
    key = "test"
    category_editor(key)
