from typing import Any

from zenlib.typing import HasLogger

from ugrd.initramfs_dict import InitramfsConfigDict


class InitramfsProtocol(HasLogger):
    config_dict: InitramfsConfigDict
    included_functions: dict[str, str | list[str]]
    build_tasks: list[str]
    init_types: list[str]


    # Add definitions for functions defining dict like behavior
    def __getattr__(self, item: str) -> Any: ...

    def __getitem__(self, item: str) -> Any: ...
