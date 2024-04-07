__author__ = "desultory"
__version__ = "0.1.3"


def start_shell(self) -> str:
    """
    Start a bash shell at the start of the initramfs.
    """
    if self["start_shell"]:
        return "bash"

