__version__ = '0.6.0'
__author__ = 'desultory'

from ugrd.fs.mounts import _get_mount_source


def _process_root_subvol(self, root_subvol: str) -> None:
    """
    processes the root subvolume
    Removes options in the root mount if they are set
    """
    self.update({'root_subvol': root_subvol})
    self.logger.debug("Set root_subvol to: %s", root_subvol)


def _process_subvol_selector(self, subvol_selector: bool) -> None:
    """
    processes the subvol selector
    """
    if subvol_selector:
        self.update({'subvol_selector': subvol_selector})
        self.logger.debug("Set subvol_selector to: %s", subvol_selector)
        self['paths'] = self['base_mount_path']


def btrfs_scan(self) -> str:
    """
    sccans for new mounts
    """
    return "btrfs device scan"


def select_subvol(self) -> str:
    """
    Returns a bash script to list subvolumes on the root volume
    """
    if not self.subvol_selector:
        self.logger.log(5, "subvol_selector not set, skipping")
        return

    root_volume = self.mounts['root']['destination']
    out = [f"btrfs subvolume list -o {root_volume}",
           "if [[ $? -ne 0 ]]; then",
           f"    echo 'Failed to list btrfs subvolumes for root volume: {root_volume}'",
           "else",
           "    echo 'Select a subvolume to use as root'",
           "    PS3='Subvolume: '",
           f"    select subvol in $(btrfs subvolume list -o {root_volume} " + "| awk '{print $9}'); do",
           "        case $subvol in",
           "            *)",
           "                if [[ -z $subvol ]]; then",
           "                    echo 'Invalid selection'",
           "                else",
           '                    echo "Selected subvolume: $subvol"',
           "                    export root_subvol=$subvol",
           "                    break",
           "                fi",
           "                ;;",
           "        esac",
           "    done",
           "fi"]
    return out


def mount_subvol(self) -> str:
    """
    mounts a subvolume
    """
    if not self.subvol_selector and not self.root_subvol:
        return

    source = _get_mount_source(self, self.mounts['root'])
    destination = self.mounts['root']['destination'] if not self.switch_root_target else self.switch_root_target

    return f"mount -o subvol=$root_subvol {source} {destination}"


def set_root_subvol(self) -> str:
    """
    sets $root_subvol
    """
    if root_subvol := self.root_subvol:
        self.masks = {'init_mount': 'mount_root'}
        return f"export root_subvol={root_subvol}"
    elif self.subvol_selector:
        base_mount_path = self.base_mount_path
        self.logger.info("Subvolume selector set, changing root_mount path to: %s", base_mount_path)
        self.switch_root_target = self.mounts['root']['destination']
        self.mounts = {'root': {'destination': base_mount_path}}

