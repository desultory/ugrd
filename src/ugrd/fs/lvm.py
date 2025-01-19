__author__ = "desultory"
__version__ = "1.5.1"

from zenlib.util import contains


def _process_lvm_multi(self, mapped_name: str, config: dict) -> None:
    self.logger.debug("[%s] Processing LVM config: %s" % (mapped_name, config))
    if "uuid" not in config:
        raise ValueError("LVM config missing uuid: %s" % mapped_name)
    self["lvm"][mapped_name] = config


@contains("early_lvm")
def early_init_lvm(self) -> None:
    """Returns shell lines to initialize LVM"""
    return init_lvm(self)


@contains("lvm", "Skipping LVM initialization, no LVM configurations found.")
def init_lvm(self) -> str:
    """Returns a shell function to initialize LVM"""
    return f"""
    einfo "[UGRD] Initializing LVM, ugrd.fs.lvm module version: {__version__}"
    einfo "$(vgchange -ay)"
    einfo "$(vgscan --mknodes)"
    """
