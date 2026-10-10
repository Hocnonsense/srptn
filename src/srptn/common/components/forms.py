"""Shared layout pieces for the New-* pages.

Keeps the New Dataset / New Analysis / New Workflow pages structurally
converged: the same meta header (categories + name on the left, description on
the right), the same resource selector placement, and the same address/occupancy
guard.
"""

from collections.abc import Callable

import streamlit as st

from srptn.common.accounts.policy import Actor
from srptn.common.data import Address, DataStore, Entity

from .categories import category_editor
from .descriptions import desc_editor
from .ui_components import persistent_text_input


def entity_meta_editor(
    key: str,
    name_label: str,
    actor: Actor,
    entity_type: type[Entity],
    data_store: DataStore,
    *,
    only_check_meta: bool = False,
    resume: Callable[[Address], bool] = lambda _: False,
):
    """Render the meta header and return the validated ``(address, desc)``.

    Stops the page while the header is incomplete.  An occupied address is
    rejected with an "already exists" error unless ``resume`` claims it (New
    Analysis / New Workflow use this to reopen an unsaved deployment rather than
    discard it); ``only_check_meta`` ignores draft data when checking occupancy.
    """
    col1, col2 = st.columns(2)
    with col1:
        categories = category_editor(f"{key}-meta")
        name = persistent_text_input(name_label, f"{key}-meta-name", "Enter name")
    with col2:
        desc: str = desc_editor(f"{key}-meta")
    if not categories or not name:
        st.stop()

    address = Address(actor.id, entity_type, categories=categories, name=name)
    if data_store.occupied(address, only_check_meta=only_check_meta):
        if not resume(address):
            st.error(f"{entity_type.__name__} {address} already exists")
            st.stop()
    return address, desc
