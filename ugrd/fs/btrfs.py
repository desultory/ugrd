__version__ = '0.3.2'
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
    if not self.config_dict.get('subvol_selector'):
        self.logger.log(5, "subvol_selector not set, skipping")
        return

    out = [f"btrfs subvolume list -o {self.config_dict['mounts']['root']['destination']}",
           "if [[ $? -ne 0 ]]; then",
           f"    echo 'Failed to list btrfs subvolumes for root volume: {self.config_dict['mounts']['root']['destination']}'",
           "else",
           "    echo 'Select a subvolume to use as root'",
           "    PS3='Subvolume: '",
           f"    select subvol in $(btrfs subvolume list -o {self.config_dict['mounts']['root']['destination']} " + "| awk '{print $9}'); do",
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
    if not self.config_dict.get('subvol_selector') and not self.config_dict.get('root_subvol'):
        return

    source = _get_mount_source(self, self.config_dict['mounts']['root'])
    destination = self.config_dict['mounts']['root']['destination'] if not self.config_dict.get('switch_root_target') else self.config_dict['switch_root_target']

    return f"mount -o subvol=$root_subvol {source} {destination}"


def set_root_subvol(self) -> str:
    """
    sets $root_subvol
    """
    if root_subvol := self.config_dict.get("root_subvol"):
        self.config_dict['masks'] = {'init_mount': 'mount_root'}
        return f"export root_subvol={root_subvol}"
    elif self.config_dict.get('subvol_selector'):
        base_mount_path = self.config_dict['base_mount_path']
        self.logger.info("Subvolume selector set, changing root_mount path to: %s", base_mount_path)
        self.config_dict['switch_root_target'] = self.config_dict['mounts']['root']['destination']
        self.config_dict['mounts'] = {'root': {'destination': base_mount_path}}

