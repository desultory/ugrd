__version__ = '0.2.0'
__author__ = 'desultory'


def _process_root_subvol(self, root_subvol: str) -> None:
    """
    processes the root subvolume
    Removes options in the root mount if they are set
    """
    self.update({'root_subvol': root_subvol})
    self.logger.debug("Set root_subvol to: %s", root_subvol)


def btrfs_scan(self) -> str:
    """
    sccans for new mounts
    """
    return "btrfs device scan"


def get_btrfs_devices(self) -> str:
    """
    Returns a bash function which uses blkid to get all btrfs devices
    """
    return "blkid -t TYPE=btrfs -o device"


def set_default_subvol(self) -> str:
    """
    selects a subvolume
    """
    if root_subvol := self.config_dict.get("root_subvol"):
        return f"btrfs subvolume set-default {root_subvol}"
    elif self.config_dict.get('subvol_selector'):
        self.logger.info("Subvolume selector set, changing root_mount path to /mnt/root_base")
        self.config_dict['mounts'] = {'root': {'destination': "/mnt/root_base"}}

