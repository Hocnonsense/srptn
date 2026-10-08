from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor
from srptn.common.components.entities import entity_browser
from srptn.common.data.entities.analysis import Analysis
from srptn.common.data.fs import fs_data_store
from srptn.views import PageInfo


@PageInfo.wrap("Analyses")
def page_analyses(actor: Actor):
    entity_browser(AccessStore(fs_data_store()), Analysis, actor)
