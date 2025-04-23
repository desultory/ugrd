__version__ = "0.1.0"

from zenlib.util import contains
from zenlib.util import colorize as c_


@contains("kmod_autodetect_input")
def autodetect_input(self):
    """ Adds _input_device_kmods to "_kmod_auto" if they are in /proc/modules"""
    with open("/proc/modules", "r") as f:
        modules = f.read()

    for input_kmod in self["_input_device_kmods"]:
        if input_kmod in modules:
            self["_kmod_auto"] = input_kmod
            self.logger.info(f"Autodetected input device kernel module: {c_(input_kmod, 'cyan')}")

