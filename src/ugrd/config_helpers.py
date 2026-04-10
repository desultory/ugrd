from pathlib import Path

from zenlib.util import parse_toml

MODULE_SEARCH_PATHS = [Path(__file__).parent, Path("/var/lib/ugrd")]


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


def get_parameters() -> dict[str, dict[str, str]]:
    """Returns a dictionary of modules and their corresponding variables
    these are defined in the "custom_paramaters" section of the config file
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
