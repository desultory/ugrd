__version__ = '1.3.0'
__author__ = 'desultory'


from zenlib.util.check_dict import check_dict


def _process_autodetect_root_subvol(self, autodetect_root_subvol: bool) -> None:
    """ Detects the root subvolume. """
    dict.__setitem__(self, 'autodetect_root_subvol', autodetect_root_subvol)


def _process_root_subvol(self, root_subvol: str) -> None:
    """ processes the root subvolume. """
    self.update({'root_subvol': root_subvol})
    self.logger.debug("Set root_subvol to: %s", root_subvol)


def _process_subvol_selector(self, subvol_selector: bool) -> None:
    """
    Processes the subvol selector parameter
    Adds the _base_mount_path to paths if enabled.
    """
    if subvol_selector:
        self.update({'subvol_selector': subvol_selector})
        self.logger.debug("Set subvol_selector to: %s", subvol_selector)
        self['paths'] = self['_base_mount_path']


def btrfs_scan(self) -> str:
    """ scan for new btrfs devices. """
    return "btrfs device scan"


@check_dict('subvol_selector', value=True, message="subvol_selector not set, skipping")
@check_dict('root_subvol', log_level=30, unset=True, message="root_subvol is set, skipping")
def select_subvol(self) -> str:
    """ Returns a bash script to list subvolumes on the root volume. """
    out = [f'mount -t btrfs -o subvolid=5,ro $(cat /run/MOUNTS_ROOT_SOURCE) {self["_base_mount_path"]}',
           f'''if [ -z "$(btrfs subvolume list -o {self['_base_mount_path']})" ]; then''',
           f'''    echo "Failed to list btrfs subvolumes for root volume: {self['_base_mount_path']}"''',
           "else",
           "    echo 'Select a subvolume to use as root'",
           "    PS3='Subvolume: '",
           f"    select subvol in $(btrfs subvolume list -o {self['_base_mount_path']} " + "| awk '{print $9}'); do",
           "        case $subvol in",
           "            *)",
           "                if [[ -z $subvol ]]; then",
           "                    echo 'Invalid selection'",
           "                else",
           '                    echo "Selected subvolume: $subvol"',
           '                    echo -n ",subvol=$subvol" >> /run/MOUNTS_ROOT_OPTIONS',
           "                    break",
           "                fi",
           "                ;;",
           "        esac",
           "    done",
           "fi",
           f"umount -l {self['_base_mount_path']}"]
    return out


def set_root_subvol(self) -> str:
    """ Adds the root_subvol to the root_mount options. """
    if root_subvol := self.get('root_subvol'):
        return f'echo -n ",subvol={root_subvol}" >> /run/MOUNTS_ROOT_OPTIONS'

