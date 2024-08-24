__version__ = '1.8.2'
__author__ = 'desultory'


from zenlib.util import contains, unset


class SubvolNotFound(Exception):
    pass


class SubvolIsRoot(Exception):
    pass


def _get_mount_subvol(self, mountpoint: str) -> list:
    """ Returns the subvolume name for a mountpoint. """
    for option in self['_mounts'][mountpoint]['options']:
        if option.startswith('subvol='):
            subvol = option.split('=')[1]
            if subvol == '/':
                raise SubvolIsRoot("Mount is at volume root: %s" % mountpoint)
            self.logger.debug("[%s] Detected subvolume: %s" % (mountpoint, subvol))
            return subvol
    raise SubvolNotFound("No subvolume detected.")


@contains('validate', "validate is not enabled, skipping root subvolume validation.")
def _validate_root_subvol(self) -> None:
    """ Validates the root subvolume. """
    try:
        detected_subvol = _get_mount_subvol(self, '/')
    except SubvolNotFound:
        if self['root_subvol']:
            raise ValueError("Current root mount is not using a subvolume, but root_subvol is set: %s" % self['root_subvol'])
    except SubvolIsRoot:
        if self['root_subvol'] != '/':
            raise ValueError("Current root mount is not using a subvolume, but root_subvol is set: %s" % self['root_subvol'])

    if self['root_subvol'] != detected_subvol:
        raise ValueError("[%s] Root subvolume does not match detected subvolume: %s" % (self['root_subvol'], detected_subvol))


def _process_root_subvol(self, root_subvol: str) -> None:
    """ processes the root subvolume. """
    self.data['root_subvol'] = root_subvol
    self.logger.debug("Set root_subvol to: %s", root_subvol)


def _process_subvol_selector(self, subvol_selector: bool) -> None:
    """
    Processes the subvol selector parameter
    Adds the _base_mount_path to paths if enabled.
    """
    if subvol_selector:
        self.data['subvol_selector'] = subvol_selector
        self.logger.debug("Set subvol_selector to: %s", subvol_selector)
        self['paths'] = self['_base_mount_path']


def btrfs_scan(self) -> str:
    """ scan for new btrfs devices. """
    return 'einfo "$(btrfs device scan)"'


@unset('subvol_selector', message="subvol_selector is enabled, skipping.", log_level=20)
@contains('autodetect_root_subvol', "autodetect_root_subvol is not enabled, skipping.", log_level=30)
@unset('root_subvol', message="root_subvol is set, skipping.")
@contains('hostonly', "hostonly is not enabled, skipping.", log_level=30)
def autodetect_root_subvol(self):
    """ Detects the root subvolume. """
    try:
        root_subvol = _get_mount_subvol(self, '/')
        self.logger.info("Detected root subvolume: %s", root_subvol)
        self['root_subvol'] = root_subvol
    except SubvolNotFound:
        self.logger.warning("Failed to detect root subvolume.")
    except SubvolIsRoot:
        self.logger.debug("Root mount is not using a subvolume.")


@contains('subvol_selector', message="subvol_selector is not enabled, skipping.")
@unset('root_subvol', message="root_subvol is set, skipping.")
def select_subvol(self) -> str:
    """ Returns a bash script to list subvolumes on the root volume. """
    # TODO: Figure out a way to make the case prompt more standard
    return [f'mount -t btrfs -o subvolid=5,ro $(readvar MOUNTS_ROOT_SOURCE) {self["_base_mount_path"]}',
            f'''if [ -z "$(btrfs subvolume list -o {self['_base_mount_path']})" ]; then''',
            f'''    ewarn "Failed to list btrfs subvolumes for root volume: {self['_base_mount_path']}"''',
            "else",
            "    echo 'Select a subvolume to use as root'",
            "    PS3='Subvolume: '",
            f"    select subvol in $(btrfs subvolume list -o {self['_base_mount_path']} " + "| awk '{print $9}'); do",
            "        case $subvol in",
            "            *)",
            "                if [[ -z $subvol ]]; then",
            "                    ewarn 'Invalid selection'",
            "                else",
            '                    einfo "Selected subvolume: $subvol"',
            '                    echo -n ",subvol=$subvol" >> /run/vars/MOUNTS_ROOT_OPTIONS',
            "                    break",
            "                fi",
            "                ;;",
            "        esac",
            "    done",
            "fi",
            f"umount -l {self['_base_mount_path']}"]


@contains('root_subvol', message="root_subvol is not set, skipping.")
def set_root_subvol(self) -> str:
    """ Adds the root_subvol to the root_mount options. """
    _validate_root_subvol(self)
    return f'''echo -n ",subvol={self['root_subvol']}" >> /run/vars/MOUNTS_ROOT_OPTIONS'''

