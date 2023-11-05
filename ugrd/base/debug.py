__author__ = "desultory"
__version__ = "0.1.0"

from pathlib import Path


def start_shell(self):
    """
    Start a bash shell at the start of the initramfs.
    """
    if self.config_dict["start_shell"]:
        return "bash"
    else:
        return None


def pull_valgrind_parts(self):
    """
    Gets the stuff which was dostrip -x'd from valgrind and adds it to the dependencies.
    """
    for file in Path('/usr/lib64/valgrind').glob('*.a'):
        self.logger.debug("Found valgrind dependency: %s", file)
        self.config_dict['dependencies'] = file
