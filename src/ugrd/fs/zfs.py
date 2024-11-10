__version__ = "0.2.0"


def zpool_import(self) -> list[str]:
    """ Returns bash lines to import all ZFS pools """
    return ["edebug 'Importing all ZFS pools'",
            'einfo "$(zpool import -a)"']
