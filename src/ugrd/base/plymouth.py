__version__ = "0.1.1"

from configparser import ConfigParser
from pathlib import Path

from zenlib.util import unset

PLYMOUTH_CONFIG_FILES = ["/etc/plymouth/plymouthd.conf", "/usr/share/plymouth/plymouthd.defaults"]


@unset("plymouth_config")
def find_plymouth_config(self) -> None:
    """Adds the plymouth config files to the build directory"""
    self.logger.info("Finding plymouthd.conf")
    for file in PLYMOUTH_CONFIG_FILES:
        plymouth_config = ConfigParser()
        plymouth_config.read(file)
        if plymouth_config.has_section("Daemon") and plymouth_config.has_option("Daemon", "Theme"):
            self["plymouth_config"] = file
            break
        self.logger.debug("Plymouth config file missing theme option: %s" % file)
    else:
        raise FileNotFoundError("Failed to find plymouthd.conf")


def _process_plymouth_config(self, file) -> None:
    """Checks that the config file is valid"""
    self.logger.info("Processing plymouthd.conf: %s" % file)
    plymouth_config = ConfigParser()
    plymouth_config.read(file)
    self["plymouth_theme"] = plymouth_config["Daemon"]["Theme"]
    self.data["plymouth_config"] = file
    self["copies"] = {"plymouth_config_file": {"source": file, "destination": "/etc/plymouth/plymouthd.conf"}}
    if device_timeout := plymouth_config.get("Daemon", "DeviceTimeout", fallback=None):
        if float(device_timeout) > 1:
            self.logger.warning("[Plymouth] DeviceTimeout is set to %s, this may cause boot delays." % device_timeout)


def _process_plymouth_theme(self, theme) -> None:
    """Checks that the theme is valid"""
    theme_dir = Path("/usr/share/plymouth/themes") / theme
    if not theme_dir.exists():
        raise FileNotFoundError("Theme directory not found: %s" % theme_dir)

    self.data["plymouth_theme"] = theme


def pull_plymouth(self) -> None:
    """Adds plymouth files to dependencies"""
    dir_list = [Path("/usr/lib64/plymouth"), Path("/usr/share/plymouth/themes/") / self["plymouth_theme"]]
    self.logger.info("[%s] Adding plymouth files to dependencies." % self["plymouth_theme"])
    for directory in dir_list:
        for file in directory.rglob("*"):
            self["dependencies"] = file


def make_devpts(self) -> list[str]:
    """Creates /dev/pts and mounts the fstab entry"""
    return ["mkdir -m755 -p /dev/pts", "mount /dev/pts"]


def start_plymouth(self) -> list[str]:
    """Returns bash lines to run plymouthd"""
    return [
        "mkdir -p /run/plymouth",
        "plymouthd --mode boot --pid-file /run/plymouth/plymouth.pid --attach-to-session",
        "setvar plymouth 1",
        "plymouth show-splash",
    ]
