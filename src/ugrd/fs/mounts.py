__author__ = 'desultory'
__version__ = '2.4.0'

from pathlib import Path

from zenlib.util import check_dict, pretty_print

MOUNT_PARAMETERS = ['destination', 'source', 'type', 'options', 'base_mount', 'skip_unmount', 'remake_mountpoint']
SOURCE_TYPES = ['uuid', 'partuuid', 'label']


@check_dict('mounts', value_arg=1, return_arg=2, contains=True)
def _merge_mounts(self, mount_name: str, mount_config) -> None:
    """ Returns merges mount config with the existing mount. """
    self.logger.info("Updating mount: %s" % mount_name)
    self.logger.debug("[%s] Updating mount with: %s" % (mount_name, mount_config))
    if 'options' in self['mounts'][mount_name] and 'options' in mount_config:
        self.logger.debug("Merging options: %s" % mount_config['options'])
        self['mounts'][mount_name]['options'] = self['mounts'][mount_name]['options'] | set(mount_config['options'])
        mount_config.pop('options')
    return dict(self['mounts'][mount_name], **mount_config)


def _validate_mount_config(self, mount_name: str, mount_config) -> None:
    """ Validate the mount config. """
    for parameter, value in mount_config.items():
        self.logger.debug("[%s] Validating parameter: %s" % (mount_name, parameter))
        if parameter == 'source' and isinstance(value, dict):
            # Break if the source type is valid
            for source_type in SOURCE_TYPES:
                if source_type in value:
                    break
            else:
                self.logger.error("Valid source types: %s" % SOURCE_TYPES)
                raise ValueError("Invalid source type in mount: %s" % value)
        elif parameter == 'options':
            for option in value:
                if 'subvol=' in option:
                    if mount_name == 'root':
                        raise ValueError("Please use the root_subvol parameter instead of setting the option manually in the root mount.")
                    elif mount_config['type'] != 'btrfs':
                        raise ValueError("subvol option can only be used with btrfs mounts.")
        elif parameter not in MOUNT_PARAMETERS:
            raise ValueError("Invalid parameter in mount: %s" % parameter)


def _process_mounts_multi(self, mount_name: str, mount_config) -> None:
    """
    Processes the passed mount config.
    Updates the mount if it already exists.
    """
    mount_config = _merge_mounts(self, mount_name, mount_config)
    _validate_mount_config(self, mount_name, mount_config)

    # Set defaults
    mount_config['destination'] = Path(mount_config.get('destination', mount_name))
    if not mount_config['destination'].is_absolute():
        mount_config['destination'] = '/' / mount_config['destination']
    mount_config['base_mount'] = mount_config.get('base_mount', False)
    mount_config['options'] = set(mount_config.get('options', ''))

    # Ensure the source is set for non-base mounts, except for the root mount. The root mount is defined empty.
    if not mount_config['base_mount'] and 'source' not in mount_config and mount_name != 'root':
        raise ValueError("[%s] No source specified in mount: %s" % (mount_name, mount_config))

    # Add imports based on the mount type
    if mount_type := mount_config.get('type'):
        if mount_type == 'vfat':
            self['kmod_init'] = 'vfat'
        elif mount_type == 'btrfs':
            if 'ugrd.fs.btrfs' not in self['modules']:
                self.logger.info("Auto-enabling module: btrfs")
                self['modules'] = 'ugrd.fs.btrfs'
        else:
            self.logger.debug("Unknown mount type: %s" % mount_type)

    self['mounts'][mount_name] = mount_config
    self.logger.debug("[%s] Added mount: %s" % (mount_name, mount_config))

    # Define the mountpoint path
    self['paths'] = mount_config['destination']


def _get_mount_source(self, mount: dict, pad=False) -> str:
    """
    returns the mount source string based on the config
    uses NAME= format so it works in both the fstab and mount command
    """
    source = mount['source']
    pad_size = 44

    out_str = ''
    if isinstance(source, dict):
        # Create the source string from the dict
        for source_type in SOURCE_TYPES:
            if source_type in source:
                out_str = f"{source_type.upper()}={source[source_type]}"
                break
    else:
        out_str = source

    if pad:
        if len(out_str) > pad_size:
            pad_size = len(out_str) + 1
        out_str = out_str.ljust(pad_size, ' ')

    return out_str


def _to_mount_cmd(self, mount: dict, check_mount=False) -> str:
    """ Prints the object as a mount command. """
    out = []

    if check_mount:
        out.append(f"if ! grep -qs {mount['destination']} /proc/mounts; then")

    mount_command = f"mount {_get_mount_source(self, mount)} {mount['destination']}"
    if options := mount.get('options'):
        mount_command += f" --options {','.join(options)}"
    if mount_type := mount.get('type'):
        mount_command += f" --types {mount_type}"

    if check_mount:
        out.append(f"    {mount_command}")
        out += ['else', f"    echo 'Mount already exists, skipping: {mount['destination']}'"]
        out.append('fi')
    else:
        out.append(mount_command)

    return out


def _to_fstab_entry(self, mount: dict) -> str:
    """
    Prints the object as a fstab entry
    The type must be specified
    """
    fs_type = mount.get('type', 'auto')
    mount_source = _get_mount_source(self, mount, pad=True)

    out_str = ''
    out_str += mount_source
    out_str += str(mount['destination']).ljust(24, ' ')
    out_str += fs_type.ljust(16, ' ')

    if options := mount.get('options'):
        out_str += ','.join(options)
    return out_str


def generate_fstab(self) -> None:
    """ Generates the fstab from the mounts. """
    fstab_info = [f"# UGRD Filesystem module v{__version__}"]

    for mount_name, mount_info in self['mounts'].items():
        if not mount_info.get('base_mount') and mount_name != 'root':
            try:
                self.logger.debug("Adding fstab entry for: %s" % mount_name)
                fstab_info.append(_to_fstab_entry(self, mount_info))
            except KeyError as e:
                self.logger.warning("Failed to add fstab entry for: %s" % mount_name)
                self.logger.warning("Required mount paramter not set: %s" % e)

    if len(fstab_info) > 1:
        self._write('/etc/fstab/', fstab_info)
    else:
        self.logger.warning("No fstab entries generated.")


def _get_dm_devices(self, f_major=None, f_minor=None) -> dict:
    """ Returns a dict of device mapper devices. Filters by major and minor if specified."""
    dm_devices = {}
    for dm_device in (Path('/sys/devices/virtual/block').iterdir()):
        if dm_device.name.startswith('dm-'):
            device_name = (dm_device / 'dm/name').read_text().strip()
            maj, minor = (dm_device / 'dev').read_text().strip().split(':')

            if f_major is not None and int(f_major) != int(maj):
                self.logger.debug("[%s] Skipping device mapper device, major mismatch: %s != %s" % (device_name, maj, f_major))
                continue
            if f_minor is not None and int(f_minor) != int(minor):
                self.logger.debug("[%s] Skipping device mapper device, minor mismatch: %s != %s" % (device_name, minor, f_minor))
                continue

            dm_devices[dm_device.name] = {}
            dm_devices[dm_device.name]['name'] = device_name
            dm_devices[dm_device.name]['major'] = maj
            dm_devices[dm_device.name]['minor'] = minor
            dm_devices[dm_device.name]['holders'] = [holder.name for holder in (dm_device / 'holders').iterdir()]
            dm_devices[dm_device.name]['slaves'] = [slave.name for slave in (dm_device / 'slaves').iterdir()]

    self.logger.debug("Found device mapper devices: %s" % dm_devices)
    return dm_devices


@check_dict('autodetect_root_luks', value=True, log_level=10, message="Skipping LUKS autodetection, autodetect_root_luks is not set.")
def _autodetect_root_luks(self, root_mount_info: dict) -> None:
    # Check if the mount is under /dev/mapper or starts with /dev/dm-
    if not root_mount_info['name'].startswith('/dev/mapper') and not root_mount_info['name'].startswith('/dev/dm-'):
        self.logger.debug("Root mount is not a device mapper mount: %s" % root_mount_info['name'])
        return
    mount_loc = Path(root_mount_info['name']).resolve()
    self.logger.debug("Detected a device mapper mount: %s" % mount_loc)

    major, minor = mount_loc.stat().st_rdev >> 8, mount_loc.stat().st_rdev & 0xFF
    self.logger.debug("[%s] Major: %s, Minor: %s" % (mount_loc, major, minor))
    dm_info = _get_dm_devices(self, major, minor)

    if len(dm_info) > 1:  # there should only be one device mapper device associated with the mount
        self.logger.error("Device mapper devices: %s" % dm_info)
        raise RuntimeError("Multiple device mapper devices found for: %s" % mount_loc)

    mapped_name, dm_info = dm_info.popitem()

    if mount_loc.name != dm_info['name'] and mount_loc.name != mapped_name:
        raise ValueError("Device mapper device name mismatch: %s != %s" % (mount_loc.name, dm_info['name']))

    if len(dm_info['holders']) > 0:
        self.logger.error("Device mapper holders: %s" % dm_info['holders'])
        raise RuntimeError("LUKS volumes should not have holders, potential LVM volume: %s" % mount_loc.name)

    if len(dm_info['slaves']) == 0:
        raise RuntimeError("No slaves found for device mapper device, unknown type: %s" % mount_loc.name)
    elif len(dm_info['slaves']) > 1:
        self.logger.error("Device mapper slaves: %s" % dm_info['slaves'])
        raise RuntimeError("Multiple slaves found for device mapper device, unknown type: %s" % mount_loc.name)

    luks_mount = _get_blkid_info(self, Path('/dev/' + dm_info['slaves'][0]))
    if luks_mount.get('type') != 'crypto_LUKS':
        if not luks_mount.get('uuid'):
            self.logger.error("[%s] Unknown device mapper slave type: %s" % (dm_info['slaves'][0], luks_mount.get('type')))
        else:
            raise RuntimeError("[%s] Unknown device mapper slave type: %s" % (dm_info['slaves'][0], luks_mount.get('type')))

    if 'ugrd.crypto.cryptsetup' not in self['modules']:
        self.logger.info("Autodetected LUKS mount, enabling the cryptsetup module: %s" % luks_mount['name'])
        self['modules'] = 'ugrd.crypto.cryptsetup'

    if uuid := luks_mount.get('uuid'):
        self.logger.info("[%s] Detected LUKS volume uuid: %s" % (mount_loc.name, uuid))
        self['cryptsetup'] = {dm_info['name']: {'uuid': uuid}}
    elif partuuid := luks_mount.get('partuuid'):
        self.logger.info("[%s] Detected LUKS volume partuuid: %s" % (mount_loc.name, partuuid))
        self['cryptsetup'] = {dm_info['name']: {'partuuid': partuuid}}

    self.logger.info("[%s] Configuring cryptsetup for LUKS mount (%s) on: %s\n%s" %
                     (mount_loc.name, dm_info['name'], luks_mount['name'], pretty_print(self['cryptsetup'])))


@check_dict('autodetect_root', value=True, log_level=10, message="Skipping root autodetection, autodetect_root is not set.")
@check_dict({'mounts': {'root': 'source'}}, unset=True, log_level=30, message="Skipping root autodetection, root source is already set.")
def autodetect_root(self) -> None:
    """ Sets self['mounts']['root']['source'] based on the host mount. """
    root_mount_info = _get_blkid_info(self, _get_mounts_source_device(self, '/'))
    self.logger.debug("Detected root mount info: %s" % root_mount_info)
    _autodetect_root_luks(self, root_mount_info)

    mount_info = {'root': {'type': 'auto', 'base_mount': False}}

    if mount_type := root_mount_info.get('type'):  # Attempt to autodetect the root type
        self.logger.info("Autodetected root type: %s" % mount_type)
        mount_info['root']['type'] = mount_type.lower()

    if label := root_mount_info.get('label'):  # Attempt to autodetect the root mount source
        self.logger.info("Autodetected root label: %s" % label)
        mount_info['root']['source'] = {'label': label}
    elif uuid := root_mount_info.get('uuid'):
        self.logger.info("Autodetected root uuid: %s" % uuid)
        mount_info['root']['source'] = {'uuid': uuid}
    else:
        raise ValueError("Failed to autodetect root mount source.")

    self['mounts'] = mount_info


def mount_base(self) -> list[str]:
    """ Generates mount commands for the base mounts. """
    out = []
    for mount in self['mounts'].values():
        if mount.get('base_mount'):
            out += _to_mount_cmd(self, mount, check_mount=True)

    return out


def remake_mountpoints(self) -> list[str]:
    """ Remakes mountpoints, especially useful when mounting over something like /dev. """
    cmds = [f"mkdir --parents {mount['destination']}" for mount in self['mounts'].values() if mount.get('remake_mountpoint')]
    if cmds:
        self['binaries'] += 'mkdir'
        return cmds


def _process_mount_timeout(self, timeout: float) -> None:
    """ Set the mount timeout, enables mount_wait. """
    if not isinstance(timeout, (int, float)):
        raise ValueError("Invalid timeout: %s" % timeout)
    if not self['mount_wait']:
        self.logger.info("Enabling mount wait, as a timeout is set: %s" % timeout)
        self['mount_wait'] = True
    dict.__setitem__(self, 'mount_timeout', timeout)


def mount_fstab(self) -> list[str]:
    """ Generates the init line for mounting the fstab. """
    out = []
    # Only wait if root_wait is specified
    if self.get('mount_wait'):
        out += [r'echo -e "\n\n\nPress enter once devices have settled.\n\n\n"']
        if timeout := self.get('mount_timeout'):
            out += [f"read -sr -t {timeout}"]
        else:
            out += ["read -sr"]

    out += ["mount -a || (echo 'Failed to mount fstab' ; _mount_fail)"]
    return out


def _pad_mountpoint(self, mountpoint: str) -> str:
    """ Pads the mountpoint with spaces. """
    mountpoint = str(mountpoint)
    mountpoint = mountpoint if mountpoint.startswith(' ') else ' ' + mountpoint
    mountpoint = mountpoint if mountpoint.endswith(' ') else mountpoint + ' '
    return mountpoint


def _get_mounts_source_options(self, mountpoint: str) -> Path:
    """ Returns the options of a mountpoint at /proc/mounts. """
    mountpoint = _pad_mountpoint(self, mountpoint)
    self.logger.debug("Getting options for: %s" % mountpoint)

    with open('/proc/mounts', 'r') as mounts:
        for line in mounts:
            if mountpoint in line:
                # If the mountpoint is found, process the options
                options = set(line.split()[3].split(','))
                self.logger.debug("[%s] Found mount options: %s" % (mountpoint, options))
                return options
    raise FileNotFoundError("Unable to find mount options for: %s" % mountpoint)


def _get_mounts_source_device(self, mountpoint: str) -> Path:
    """ Returns the source device of a mountpoint at /proc/mounts. """
    mountpoint = _pad_mountpoint(self, mountpoint)
    self.logger.debug("Getting source device path for: %s" % mountpoint)

    with open('/proc/mounts', 'r') as mounts:
        for line in mounts:
            if mountpoint in line:
                # If the mountpoint is found, return the source
                # Resolve the path as it may be a symlink
                mount_source = Path(line.split()[0]).resolve()
                self.logger.debug("[%s] Found mount source: %s" % (mountpoint, mount_source))
                return mount_source
    raise FileNotFoundError("Unable to find mount source device for: %s" % mountpoint)


def _get_blkid_info(self, device: Path) -> str:
    """ Gets the blkid info for a device. """
    from subprocess import run
    self.logger.debug("Getting blkid info for: %s" % device)

    cmd = run(['blkid', str(device)], capture_output=True)
    if cmd.returncode != 0:
        self.logger.warning("Unable to find blkid info for: %s" % device)
        return None

    blkid_info = cmd.stdout.decode().strip()

    if not blkid_info:
        self.logger.warning("Unable to find blkid info for: %s" % device)
        return None

    self.logger.debug("[%s] Got blkid info: %s" % (device, blkid_info))

    mount_name, mount_info = blkid_info.split(': ')
    mount_dict = {key.lower(): value.strip('"') for key, value in (mount_info.split('=') for mount_info in mount_info.split(' '))}
    mount_dict['name'] = mount_name
    self.logger.log(5, "Parsed blkid info: %s" % mount_dict)
    return mount_dict


@check_dict('validate', value=True, log_level=20, return_val=True, message="Skipping host mount validation.")
def _validate_host_mount(self, mount, destination_path=None) -> bool:
    """ Checks if a defined mount exists on the host. """
    source = mount['source']
    # If a destination path is passed, like for /, use that instead of the mount's destination
    destination_path = mount['destination'] if destination_path is None else destination_path

    # This will raise a FileNotFoundError if the mountpoint doesn't exist
    host_source_dev = _get_mounts_source_device(self, destination_path)

    # The returned value should equal the mount source if it's a string
    if isinstance(source, str):
        if source != host_source_dev:
            self.logger.warning("Host device mismatch. Expected: %s, Found: %s" % (source, host_source_dev))
    elif isinstance(source, dict):
        # If the source is a dict, check that the uuid, partuuid, or label matches the host mount
        if blkid_info := _get_blkid_info(self, host_source_dev):
            # Unholy for-else, breaks if the uuid, partuuid, or label matches, otherwise warns
            for key, value in source.items():
                if blkid_info.get(key) == value:
                    self.logger.debug("[%s] Found host device match, key '%s' == '%s' " % (host_source_dev, key, value))
                    return True
            else:
                self.logger.error("Mount device not found on host system. Expected: %s" % source)
                self.logger.error("Host device info: %s" % blkid_info)
        else:
            self.logger.warning("Unable to find blkid info for: %s" % host_source_dev)

    raise ValueError("Unable to validate host mount: %s" % mount)


def mount_root(self) -> str:
    """
    Mounts the root partition to $MOUNTS_ROOT_TARGET.
    Warns if the root partition isn't found on the current system.
    """
    if not _validate_host_mount(self, self['mounts']['root'], '/'):
        self.logger.error("Unable to validate root mount. Please ensure the root partition is mounted on the host system or disable validation.")

    return ['''echo "Mounting '$(cat /run/MOUNTS_ROOT_SOURCE)' to '$(cat /run/MOUNTS_ROOT_TARGET)' with options: $(cat /run/MOUNTS_ROOT_OPTIONS)"''',
            'mount "$(cat /run/MOUNTS_ROOT_SOURCE)" "$(cat /run/MOUNTS_ROOT_TARGET)" -o "$(cat /run/MOUNTS_ROOT_OPTIONS)"']


@check_dict({'mounts': {'root': 'source'}}, log_level=20, raise_exception=True, message="Root mount source is not defined.")
def export_mount_info(self) -> None:
    """ Exports mount info based on the config to /run/MOUNTS_ROOT_{option} """
    return [f'echo -n "{self["mounts"]["root"]["destination"]}" > "/run/MOUNTS_ROOT_TARGET"',
            f'echo -n "{_get_mount_source(self, self["mounts"]["root"])}" > "/run/MOUNTS_ROOT_SOURCE"',
            f'''echo -n "{','.join(self["mounts"]["root"]["options"])}" > "/run/MOUNTS_ROOT_OPTIONS"''']


def clean_mounts(self) -> list[str]:
    """ Generates init lines to unmount all mounts. """
    umounts = [f"umount {mount['destination']}" for mount in self['mounts'].values() if not mount.get('skip_unmount')]
    # Ensure /proc is unmounted last
    if 'umount /proc' in umounts and umounts[-1] != 'umount /proc':
        umounts.remove('umount /proc')
        umounts.append('umount /proc')

    return ['umount -a'] + umounts


def _mount_fail(self) -> list[str]:
    """ Generates init lines to run if the mount fails. """
    return ['echo "Loaded modules:"',
            'lsmod',
            'echo "Block devices:"',
            'blkid',
            'echo "Mounts:"',
            'mount',
            r'echo -e "\n\n\nPress enter to restart init\n\n\n"',
            'read -sr',
            'if [ "$$" -eq 1 ]; then',
            '    echo "Restarting init"',
            '    exec /init',
            'else',
            '    echo "PID is not 1, exiting: $$"',
            '    exit',
            'fi']


