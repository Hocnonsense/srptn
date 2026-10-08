"""Single source of truth for page availability.

Each page is registered here with its title and the minimum role required.
Both the navigation (sidebar) and the page itself go through this registry,
so "can see it" and "can open it" always agree.  ``min_role`` of ``None``
means any authenticated role.

A page's ``source`` is either a callable (wrapped so it enforces the role
before rendering) or a path to a script page.
"""

import functools
from collections.abc import Callable
from typing import NamedTuple

import streamlit as st

from srptn.common.accounts.policy import Role, Actor


class PageInfo(NamedTuple):
    source: Callable[[Actor], None] | str
    title: str
    min_role: Role | None

    def permitted(self, actor: Actor):
        """Return whether ``actor`` is permitted to see this page."""
        return actor.role.permitted(self.min_role)

    def page(self, actor: Actor):
        source = self.source
        if isinstance(source, str):
            return source

        @functools.wraps(source)
        def render():
            if not actor.role.permitted(self.min_role):
                st.error("You do not have permission to view this page.")
                st.stop()
            source(actor)

        return render


def visible_pages(actor: Actor):
    """The pages ``actor`` may see in the navigation."""
    from .analyses import page_analyses
    from .analysis_new import page_new_analysis
    from .dataset_new import page_new_dataset
    from .datasets import page_datasets
    from .workflow_new import page_new_workflow

    PAGES = (
        PageInfo(page_new_dataset, "New Dataset", Role.HOST),
        PageInfo(page_datasets, "Datasets", None),
        PageInfo(page_new_workflow, "New Workflow", Role.PUBLISHER),
        PageInfo(page_new_analysis, "New Analysis", Role.HOST),
        PageInfo(page_analyses, "Analyses", None),
        PageInfo("views/5 Notebook (Mockup).py", "Notebook (Mockup)", None),
        PageInfo("views/6 Compose Figure (Mockup).py", "Compose Figure (Mockup)", None),
    )
    for page in PAGES:
        if page.permitted(actor):
            yield st.Page(page.page(actor), title=page.title)
