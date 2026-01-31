from pathlib import Path

from zenlib.util import colorize as c_

from ugrd.exceptions import AutodetectError


def _get_udev_rule_progs(rule_file: Path):
    """Extracts programs called by a udev rule file"""

    progs = set()

    with rule_file.open("r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or not line or "IMPORT{program}" not in line:
                continue

            progname = line[line.index("IMPORT{program}") + 17 :].split()[0].strip('";, ')
            progs.add(progname)

    return list(progs)


def pull_udev_deps(self):
    """Pulls udev rule files"""

    udev_rule_dirs = [Path("/etc/udev/rules.d"), Path("/lib/udev/rules.d")]

    for rule_dir in udev_rule_dirs:
        for rule_file in rule_dir.glob("*.rules"):
            self["dependencies"] = rule_file
            if progs := _get_udev_rule_progs(rule_file):
                self.logger.info(
                    f"[{c_(rule_file.name, 'blue')}] Found binary requirements: {c_(', '.join(progs), 'green')}"
                )
                try:
                    self["binaries"] = progs
                except AutodetectError as e:
                    self.logger.warning(f"[{c_(rule_file.name, 'red')}] Unable to find udev rule dependency: {e}")


def start_udev(self):
    """Returns shell lines to start udev"""
    return """
    edebug "Starting udev: $(/lib/systemd/systemd-udevd --daemon 2>&1)"
    udevadm trigger"""
