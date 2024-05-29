__author__ = "desultory"
__version__ = "1.0.1"


def start_shell(self) -> str:
    """
    Start a bash shell at the start of the initramfs.
    """
    if self["start_shell"]:
        return [f"einfo '\n\nStarting debug module version: {__version__}\n\n'", "bash"]

