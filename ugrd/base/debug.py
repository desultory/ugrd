__author__ = "desultory"
__version__ = "0.1.0"


def start_shell(self):
    """
    Start a bash shell at the start of the initramfs.
    """
    if self.config_dict["start_shell"]:
        return "bash"
    else:
        return None
