from typing import Any, Protocol

from zenlib.typing import HasLogger

from ugrd import InitramfsConfig


class InitramfsProtocol(HasLogger, Protocol):
    config_dict: InitramfsConfig
    included_functions: dict[str, str | list[str]]
    build_tasks: list[str]
    init_types: list[str]

    # Add basic definitions for functions defining dict like behavior
    def get(self, item: str, default: Any = None) -> Any: ...
    def __getitem__(self, item: str) -> Any: ...
    def __setitem__(self, item: str, value: Any) -> None: ...
    def __contains__(self, key: str) -> bool: ...
