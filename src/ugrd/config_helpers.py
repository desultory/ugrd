from pathlib import Path
from typing import Any

from pycpio import PyCPIO
from zenlib.types import NoDupFlatList
from zenlib.util import parse_toml

DEFAULT_CONFIG_PATH = "/etc/ugrd/config.toml"
MODULE_SEARCH_PATHS = [Path(__file__).parent, Path("/var/lib/ugrd")]

ALLOWED_PARAMETER_TYPES: dict[str, type] = {
    t.__name__: t for t in (bool, str, int, float, dict, list, Path, NoDupFlatList, PyCPIO)
}


def get_module_paths() -> list[Path]:
    """Returns a list of paths to module config files, based on the MODULE_SEARCH_PATHS variable."""
    module_paths: list[Path] = []
    for search_path in MODULE_SEARCH_PATHS:
        module_paths.extend(Path(search_path).rglob("*.toml"))
    return module_paths


def get_module_name(module_path: Path) -> str:
    """Returns the normalized module name given the path of the module config file"""
    module_name = module_path.stem
    parent_name = "" if module_path.is_relative_to("/var/lib/ugrd") else "ugrd."
    while module_path.parent.name != "ugrd":
        parent_name += module_path.parent.name + "."
        module_path = module_path.parent
    return parent_name + module_name


def read_ugrd_module(module_name: str) -> dict[str, Any]:
    """Reads a ugrd module given a module name. Returns the config"""
    for module in get_module_paths():
        if module_name == get_module_name(module):
            return parse_toml(module)

    raise FileNotFoundError(f"Unable to find module: {module_name}")


def resolve_type(type_name: str) -> type:
    """Resolves a type name to a type"""
    try:
        return ALLOWED_PARAMETER_TYPES[type_name]
    except KeyError as e:
        raise ValueError(f"Unknown type: {type_name}, Allowed types: {ALLOWED_PARAMETER_TYPES}") from e


def get_parameters() -> dict[str, dict[str, str]]:
    """Returns a dictionary of modules and their corresponding variables
    these are defined in the "custom_parameters" section of the config file
    """
    parameters = {}
    for module in get_module_paths():
        try:
            config = parse_toml(module)
        except Exception as e:
            print(f"!!! Failed to parse {module}:\n{e}")
            continue
        if "custom_parameters" in config:
            module_name = get_module_name(module)
            parameters[module_name] = config["custom_parameters"]
    return parameters
