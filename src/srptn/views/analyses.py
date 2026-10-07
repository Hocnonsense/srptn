from srptn.common.accounts.policy import Actor
from srptn.common.components.entities import entity_browser
from srptn.common.data.entities.analysis import Analysis
from srptn.common.data.fs import FSDataStore


def page_analyses(actor: Actor):
    data = FSDataStore()

    entity_browser(data, Analysis, actor)
