import re

import yaml

SCIENTIFIC_FLOAT = re.compile(r"^\d+(\.\d+)?[eE][-+]?\d+$")


class CustomSafeLoader(yaml.SafeLoader):
    """Custom YAML loader."""

    def scientificfloat_as_string(
        self,
        node: yaml.nodes.ScalarNode,
    ):
        """Load scientific floats as strings if in scientific notation."""
        value = self.construct_scalar(node)
        # Check if the value looks like a float in scientific notation
        if SCIENTIFIC_FLOAT.match(value):
            return value
        return float(value)


CustomSafeLoader.add_constructor(
    "tag:yaml.org,2002:float", CustomSafeLoader.scientificfloat_as_string
)


class CustomSafeDumper(yaml.SafeDumper):
    """Custom YAML dumper."""

    def scientificfloat_from_string_as_float(
        self,
        value: str,
    ):
        """Dump scientific float from a string to yaml as float."""
        if re.match(r"^\d+(\.\d+)?[eE][-+]?\d+scn$", value):
            return self.represent_scalar(
                "tag:yaml.org,2002:float",
                value[:-3],  # Remove the custom 'scn' suffix and represent as float
            )
        return self.represent_scalar("tag:yaml.org,2002:str", value)


CustomSafeDumper.add_representer(
    str, CustomSafeDumper.scientificfloat_from_string_as_float
)
