from typing import Union


def _normalize_kmod_name(module: Union[str, list]) -> str:
    """ Replaces -'s with _'s in a kernel module name. """
    if isinstance(module, list) and not isinstance(module, str):
        return [_normalize_kmod_name(m) for m in module]
    return module.replace('-', '_')


class DependencyResolutionError(Exception):
    pass


class BuiltinModuleError(Exception):
    pass


class IgnoredModuleError(Exception):
    pass

