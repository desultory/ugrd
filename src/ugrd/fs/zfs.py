__version__ = "0.2.2"
from ugrd import InitramfsProtocol


def zpool_import(self: InitramfsProtocol) -> str:
    """Returns bash lines to import all ZFS pools"""
    return """
    edebug 'Importing all ZFS pools'
    export ZPOOL_IMPORT_UDEV_TIMEOUT_MS=0  # Disable udev timeout
    einfo "$(zpool import -aN)"
    """
