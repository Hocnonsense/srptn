"""Shared layout pieces for the New-* pages.

Keeps the New Dataset / New Analysis / New Workflow pages structurally
converged: the same meta header (categories + name on the left, description on
the right) and the same resource selector placement.
"""

import streamlit as st

from .categories import category_editor
from .descriptions import desc_editor
from .ui_components import persistent_text_input


def entity_meta_editor(key: str, name_label: str):
    """Render the converged meta header and return ``(categories, name, desc)``."""
    col1, col2 = st.columns(2)
    with col1:
        categories = category_editor(f"{key}-meta")
        name = persistent_text_input(name_label, f"{key}-meta-name", "Enter name")
    with col2:
        desc = desc_editor(f"{key}-meta")
    return categories, name, desc
