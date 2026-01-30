
from pathlib import Path


def pull_udev_deps(self):
    """ Pulls udev rule files """

    udev_rule_dir = Path("/etc/udev/rules.d")

    for rule_file in udev_rule_dir.glob("*.rules"):
        self["dependencies"] = rule_file


def start_udev(self):
    """ Returns shell lines to start udev """
    return """
    /lib/systemd/systemd-udevd --daemon
    udevadm trigger"""



