__author__ = "desultory"
__version__ = "1.2.0"

from zenlib.util import contains
from pathlib import Path


def _process_sc_public_key(self, key: str) -> None:
    """Processes the smartcard public key file."""
    key_path = Path(key)
    if not key_path.exists():
        raise FileNotFoundError(f"Smartcard public key file not found: {key}")
    self.data["sc_public_key"] = key_path
    self.logger.info("Using smartcard public key file: %s", key_path)
    self["dependencies"] = key_path


@contains("sc_public_key", "Smartcard public key file not specified (sc_public_key)", raise_exception=True)
def import_keys(self) -> str:
    """Import GPG public keys at runtime."""
    return f'einfo "Importing GPG keys: $(gpg --import {self['sc_public_key']} 2>&1)"'
