__author__ = "desultory"
__version__ = "0.2.0"


def print_banner(self) -> list[str]:
    """Prints the banner. Prints the kernel version if set"""
    banner = [self.banner]
    if kver := self.get("kernel_version"):
        banner.append(f"einfo 'Built for kernel version: {kver}'")
    return banner
