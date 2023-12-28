__version__ = '1.3.0'
__author__ = 'desultory'


from ugrd.fs.mounts import _get_mounts_source_options
from zenlib.util.check_dict import check_dict


class SubvolNotFound(Exception):
    pass


class SubvolIsRoot(Exception):
    pass


def _get_mount_subvol(self, mountpoint: str) -> list:
    """ Returns the subvolume name for a mountpoint. """
    for option in _get_mounts_source_options(self, mountpoint):
        if option.startswith('subvol='):
            subvol = option.split('=')[1]
            if subvol == '/':
                raise SubvolIsRoot("Mount is at volume root: %s" % mountpoint)
            self.logger.info("[%s] Detected subvolume: %s" % (mountpoint, subvol))
            return subvol
    raise SubvolNotFound("No subvolume detected.")


@check_dict('validate', value=True, message="Validate is not set, skipping root subvolume validation.")
def _validate_root_subvol(self) -> None:
    """ Validates the root subvolume. """
    try:
        detected_subvol = _get_mount_subvol(self, '/')
    except SubvolNotFound:
        raise ValueError("Current root mount is not using a subvolume, but root_subvol is set: %s" % self['root_subvol'])
    if self['root_subvol'] != detected_subvol:
        raise ValueError("[%s] Root subvolume does not match detected subvolume: %s" % (self['root_subvol'], detected_subvol))


def _process_root_subvol(self, root_subvol: str) -> None:
    """ processes the root subvolume. """
    self.update({'root_subvol': root_subvol})
    _validate_root_subvol(self)
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


@check_dict('root_subvol', unset=True, log_level=30, message="root_subvol is set, skipping")
@check_dict('subvol_selector', value=False, log_level=20, message="subvol_selector enabled, skipping")
@check_dict('autodetect_root_subvol', value=True, message="autodetect_root_subvol not enabled, skipping")
def autodetect_root_subvol(self):
    """ Detects the root subvolume. """
    try:
        self['root_subvol'] = _get_mount_subvol(self, '/')
    except SubvolNotFound:
        self.logger.warning("Failed to detect root subvolume.")
    except SubvolIsRoot:
        self.logger.debug("Root mount is not using a subvolume.")


@check_dict('subvol_selector', value=True, message="subvol_selector not enabled, skipping")
@check_dict('root_subvol', log_level=30, unset=True, message="root_subvol is set, skipping")
def select_subvol(self) -> str:
    """ Returns a bash script to list subvolumes on the root volume. """
    return [f'mount -t btrfs -o subvolid=5,ro $(cat /run/MOUNTS_ROOT_SOURCE) {self["_base_mount_path"]}',
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


@check_dict('root_subvol', message="root_subvol is not set, skipping")
def set_root_subvol(self) -> str:
    """ Adds the root_subvol to the root_mount options. """
    return f'''echo -n ",subvol={self['root_subvol']}" >> /run/MOUNTS_ROOT_OPTIONS'''

