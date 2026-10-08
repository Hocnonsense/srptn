from .analysis import Analysis
from .dataset import Dataset
from .workflow import Workflow

_entity_types = {i.__name__.lower(): i for i in (Analysis, Dataset, Workflow)}
