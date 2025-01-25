__author__ = "desultory"
__version__ = "2.1.0"

from zenlib.util import colorize, contains


def _process_lvm_multi(self, mapped_name: str, config: dict) -> None:
    self.logger.debug("[%s] Processing LVM config: %s" % (mapped_name, config))
    if "uuid" not in config:
        raise ValueError("LVM config missing uuid: %s" % mapped_name)
    if "holders" in config:
        if not self["early_lvm"]:
            self.logger.info(
                "[%s] LVM volume has holders, enabling early_lvm: %s"
                % (mapped_name, colorize(", ".join(config["holders"]), "cyan"))
            )
            self["early_lvm"] = True
    self["lvm"][mapped_name] = config


@contains("early_lvm")
@contains("lvm", "Skipping early LVM initialization, no LVM configurations found.", log_level=30)
def early_lvm(self) -> str:
    """If early_lvm is set, return a shell function to initialize LVM"""
    return "init_lvm 'Early initialzing LVM'"


@contains("lvm", "Skipping LVM initialization, no LVM configurations found.", log_level=30)
def init_lvm(self) -> str:
    """Returns a shell function to initialize LVM"""
    return f"""
    msg="${{1:-Initializing LVM}}"
    einfo "[UGRD] "$msg", ugrd.fs.lvm module version: {__version__}"
    einfo "$(vgchange -ay)"
    einfo "$(vgscan --mknodes)"
    """
