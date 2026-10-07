from srptn.common.accounts.session import require_actor
from srptn.common.components.entities import entity_browser
from srptn.common.data.entities.analysis import Analysis
from srptn.common.data.fs import FSDataStore

actor = require_actor()
data = FSDataStore()

entity_browser(data, Analysis, actor)
