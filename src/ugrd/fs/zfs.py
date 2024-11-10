__version__ = "0.1.0"


def zpool_import(self) -> str:
    """ Returns bash lines to import all ZFS pools """
    return "zpool import -a"
