__author__ = "desultory"
__version__ = "1.2.2"
from pathlib import Path

from ugrd import InitramfsConfig, InitramfsProtocol
from zenlib.util import colorize, contains


def _process_sc_public_key(self: InitramfsConfig, key: str) -> None:
    """Processes the smartcard public key file."""
    key_path = Path(key)
    if not key_path.exists():
        raise FileNotFoundError(f"Smartcard public key file not found: {key}")
    self.data["sc_public_key"] = key_path
    self.logger.info("Using smartcard public key file: %s", colorize(key_path, "green"))
    self["dependencies"] = key_path


@contains("sc_public_key", "Smartcard public key file not specified (sc_public_key)", raise_exception=True)
def import_keys(self: InitramfsProtocol) -> str:
    """Import GPG public keys at runtime."""
    return f'''einfo "Importing GPG keys: $(gpg --import {self["sc_public_key"]} 2>&1)"'''
