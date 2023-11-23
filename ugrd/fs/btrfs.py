__version__ = '0.2.0'
__author__ = 'desultory'


def _process_root_subvol(self, root_subvol: str) -> None:
    """
    processes the root subvolume
    Removes options in the root mount if they are set
    """
    if 'options' in self['mounts']['root']:
        for option in self['mounts']['root']['options']:
            if option.startswith("subvol"):
                self.logger.warning("Manual subvolume option set in root mount when root_subvol is set in config, removing.")
                self['mounts']['root']['options'].remove(option)

    self.update({'root_subvol': root_subvol})


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


def select_subvol(self) -> str:
    """
    selects a subvolume
    """
    out = []
    if root_subvol := self.config_dict.get("root_subvol"):
        out.append(f"btrfs subvolume set-default {root_subvol}")

    return out



