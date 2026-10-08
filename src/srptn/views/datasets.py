from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor
from srptn.common.components.entities import entity_browser
from srptn.common.data.entities.dataset import Dataset
from srptn.common.data.fs import fs_data_store

from srptn.views import PageInfo


@PageInfo.wrap("Datasets")
def page_datasets(actor: Actor):
    entity_browser(AccessStore(fs_data_store()), Dataset, actor)
