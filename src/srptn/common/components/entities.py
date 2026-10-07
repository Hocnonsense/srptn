import streamlit as st

from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor
from srptn.common.data import Address, Entity
from srptn.common.data.entities.dataset import Dataset

from .ui_components import persistent_multiselect


def entity_browser(access: AccessStore, entity_type: type[Entity], actor: Actor):
    """Browse entities the actor may read (self + public).

    The actor's own entries get a Public/Unpublish toggle.
    """
    search_term = st.text_input("Search")
    only_mine = st.checkbox("only mine")

    entities = access.entities(
        actor, entity_type, search_term=search_term, only_owned=only_mine
    )

    if not entities:
        st.warning(f"No {entity_type.__name__.lower()} found")
        return

    for entity in entities:
        entity.show(actor, access=access)
        if entity.address.owner == actor.id:
            _visibility_control(access, actor, entity.address)


def _visibility_control(access: AccessStore, actor: Actor, address: Address):
    public = access.is_public(address)
    if st.button("Unpublish" if public else "Publish", key=f"publish-{address}"):
        access.set_publish(actor, address, not public)
        st.rerun()


def data_selector(access: AccessStore, actor: Actor, key: str):
    """Allow the actor to select from datasets it may read (self + public)."""
    entities = access.entities(actor, Dataset)

    if entities:
        names = [str(entity.address) for entity in entities]
        selected = persistent_multiselect(
            "Select datasets",
            names,
            key,
        )
        entities = [entity for entity in entities if str(entity.address) in selected]
        st.session_state["workflow-meta-datasets-sheets"] = {
            str(entity.address): entity.sheet for entity in entities
        }
        return entities
    st.warning("No Dataset found")
    return []
