__author__ = 'desultory'
__version__ = '1.2.2'

from zenlib.util import contains


def _process_lvm_multi(self, mapped_name: str, config: dict) -> None:
    self.logger.debug("[%s] Processing LVM config: %s" % (mapped_name, config))
    if 'uuid' not in config:
        raise ValueError("LVM config missing uuid: %s" % mapped_name)
    self['lvm'][mapped_name] = config


@contains('lvm', "Skipping LVM initialization, no LVM configurations found.")
def init_lvm(self) -> None:
    """ Returns bash lines to initialize LVM """
    return ['einfo "Initializing LVM, module version %s"' % __version__,
            'einfo "$(vgchange -ay)"',
            'einfo "$(vgscan --mknodes)"']
