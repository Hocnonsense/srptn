from srptn.common.accounts.policy import Actor
from srptn.common.components.entities import entity_browser
from srptn.common.data.entities.dataset import Dataset
from srptn.common.data.fs import FSDataStore


def page_datasets(actor: Actor):
    data = FSDataStore()

    entity_browser(data, Dataset, actor)
