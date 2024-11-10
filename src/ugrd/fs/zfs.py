__version__ = "0.2.1"


def zpool_import(self) -> list[str]:
    """ Returns bash lines to import all ZFS pools """
    return ["edebug 'Importing all ZFS pools'",
            'export ZPOOL_IMPORT_UDEV_TIMEOUT_MS=0',  # Disable udev timeout
            'einfo "$(zpool import -a)"']
