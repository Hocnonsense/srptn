from srptn.common.access.store import AccessStore
from srptn.common.accounts.policy import Actor, Role
from srptn.common.components.entities import entity_browser
from srptn.common.data.entities.workflow import Workflow
from srptn.common.data.fs import fs_data_store
from srptn.views import PageInfo


@PageInfo.wrap("Workflows", Role.PUBLISHER)
def page_workflows(actor: Actor):
    entity_browser(AccessStore(fs_data_store()), Workflow, actor)
