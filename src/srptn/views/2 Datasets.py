from srptn.common.accounts.session import require_actor
from srptn.common.components.entities import entity_browser
from srptn.common.data.entities.dataset import Dataset
from srptn.common.data.fs import FSDataStore

actor = require_actor()
owner = actor.id
data = FSDataStore()

entity_browser(data, Dataset, owner)
