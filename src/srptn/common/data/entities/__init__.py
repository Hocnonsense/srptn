from .analysis import Analysis
from .dataset import Dataset

_entity_types: dict[str, type[Analysis] | type[Dataset]] = {
    "dataset": Dataset,
    "analysis": Analysis,
}
