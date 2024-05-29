__author__ = 'desultory'
__version__ = '3.4.0'

from pathlib import Path
from zenlib.util import check_dict, pretty_print

BLKID_FIELDS = ['uuid', 'partuuid', 'label', 'type']
SOURCE_TYPES = ['uuid', 'partuuid', 'label', 'path']
MOUNT_PARAMETERS = ['destination', 'source', 'type', 'options', 'base_mount', 'remake_mountpoint', *SOURCE_TYPES]


def _validate_mount_config(self, mount_name: str, mount_config) -> None:
    """ Validate the mount config. """
    if any(source_type in mount_config for source_type in SOURCE_TYPES):
        self.logger.debug("[%s] Found source type: %s" % (mount_name, mount_config))
    elif 'source' not in mount_config and mount_name != 'root':  # Don't require source for the root mount, it is defined empty
        raise ValueError("[%s] No source type found in mount: %s" % (mount_name, mount_config))

    for parameter, value in mount_config.copy().items():
        self.logger.debug("[%s] Validating parameter: %s" % (mount_name, parameter))
        if parameter == 'source' and isinstance(value, dict):
            self.logger.warning("source dict is deprecated, please define the source type directly")
            self.logger.info("Simply define the source type directly in the mount config, instead of using the 'source' dict.")
            # Break if the source type is valid
            for source_type in SOURCE_TYPES:
                if source_type in value:
                    mount_config[source_type] = value[source_type]
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


def _merge_mounts(self, mount_name: str, mount_config, mount_class) -> None:
    """ Merges the passed mount config with the existing mount. """
    if mount_name not in self[mount_class]:
        self.logger.debug("[%s] Skipping mount merge, mount not found: %s" % (mount_class, mount_name))
        return mount_config

    self.logger.info("[%s] Updating mount: %s" % (mount_class, mount_name))
    self.logger.debug("[%s] Updating mount with: %s" % (mount_name, mount_config))
    if 'options' in self[mount_class][mount_name] and 'options' in mount_config:
        self.logger.debug("Merging options: %s" % mount_config['options'])
        self[mount_class][mount_name]['options'] = self[mount_class][mount_name]['options'] | set(mount_config['options'])
        mount_config.pop('options')

    return dict(self[mount_class][mount_name], **mount_config)


def _process_mount(self, mount_name: str, mount_config, mount_class="mounts") -> None:
    """ Processes the passed mount config. """
    mount_config = _merge_mounts(self, mount_name, mount_config, mount_class)
    _validate_mount_config(self, mount_name, mount_config)

    # Set defaults
    mount_config['destination'] = Path(mount_config.get('destination', mount_name))
    if not mount_config['destination'].is_absolute():
        mount_config['destination'] = '/' / mount_config['destination']
    mount_config['base_mount'] = mount_config.get('base_mount', False)
    mount_config['options'] = set(mount_config.get('options', ''))

    # Add imports based on the mount type
    if mount_type := mount_config.get('type'):
        if mount_type in ['vfat', 'ext4', 'xfs']:
            self['kmod_init'] = mount_type
        elif mount_type == 'btrfs':
            if 'ugrd.fs.btrfs' not in self['modules']:
                self.logger.info("Auto-enabling module: btrfs")
                self['modules'] = 'ugrd.fs.btrfs'
        elif mount_type not in ['proc', 'sysfs', 'devtmpfs', 'tmpfs']:
            self.logger.warning("Unknown mount type: %s" % mount_type)

    self[mount_class][mount_name] = mount_config
    self.logger.debug("[%s] Added mount: %s" % (mount_name, mount_config))

    if mount_class == 'mounts':
        # Define the mountpoint path for standard mounts
        self['paths'] = mount_config['destination']


def _process_mount_timeout(self, timeout: float) -> None:
    """ Set the mount timeout, enables mount_wait. """
    if not isinstance(timeout, (int, float)):
        raise ValueError("Invalid timeout: %s" % timeout)
    if not self['mount_wait']:
        self.logger.info("Enabling mount wait, as a timeout is set: %s" % timeout)
        self['mount_wait'] = True
    dict.__setitem__(self, 'mount_timeout', timeout)


def _process_mounts_multi(self, mount_name: str, mount_config) -> None:
    _process_mount(self, mount_name, mount_config)


def _process_late_mounts_multi(self, mount_name: str, mount_config) -> None:
    _process_mount(self, mount_name, mount_config, 'late_mounts')


def _get_mount_source_type(self, mount: dict, with_val=False) -> str:
    """ Gets the source from the mount config. """
    for source_type in SOURCE_TYPES:
        if source_type in mount:
            if with_val:
                return source_type, mount[source_type]
            return source_type
    raise ValueError("No source type found in mount: %s" % mount)


def _get_mount_str(self, mount: dict, pad=False, pad_size=44) -> str:
    """ returns the mount source string based on the config,
    the output string should work with fstab and mount commands.
    pad: pads the output string with spaces, defined by pad_size (44)."""
    mount_type, mount_name = _get_mount_source_type(self, mount, with_val=True)
    out_str = mount_name if mount_type == 'path' else f"{mount_type.upper()}={mount_name}"

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

    mount_command = f"mount {_get_mount_str(self, mount)} {mount['destination']}"
    if options := mount.get('options'):
        mount_command += f" --options {','.join(options)}"
    if mount_type := mount.get('type'):
        mount_command += f" -t {mount_type}"

    mount_command += f" || _mount_fail 'failed to mount: {mount['destination']}'"

    if check_mount:
        out.append(f"    {mount_command}")
        out += ['else', f"    ewarn 'Mount already exists, skipping: {mount['destination']}'"]
        out.append('fi')
    else:
        out.append(mount_command)

    return out


def _to_fstab_entry(self, mount: dict) -> str:
    """
    Prints the object as a fstab entry
    The type must be specified
    """
    _validate_host_mount(self, mount)
    fs_type = mount.get('type', 'auto')

    out_str = _get_mount_str(self, mount, pad=True)
    out_str += str(mount['destination']).ljust(24, ' ')
    out_str += fs_type.ljust(16, ' ')

    if options := mount.get('options'):
        out_str += ','.join(options)
    return out_str


def generate_fstab(self, mount_class="mounts", filename="/etc/fstab") -> None:
    """ Generates the fstab from the specified mounts. """
    fstab_info = [f"# UGRD Filesystem module v{__version__}"]

    for mount_name, mount_info in self[mount_class].items():
        if not mount_info.get('base_mount') and mount_name != 'root':
            try:
                self.logger.debug("[%s] Adding fstab entry for: %s" % (mount_class, mount_name))
                fstab_info.append(_to_fstab_entry(self, mount_info))
            except KeyError as e:
                self.logger.warning("[%s] Failed to add fstab entry for: %s" % (mount_class, mount_name))
                self.logger.warning("Required mount paramter not set: %s" % e)

    if len(fstab_info) > 1:
        self._write(filename, fstab_info)
    else:
        self.logger.debug("[%s] No fstab entries generated for mounts: %s" % (mount_class, ', '.join(self[mount_class].keys())))


def get_blkid_info(self) -> str:
    """ Gets the blkid info for all device. """
    from re import search
    blkid_output = self._run(['blkid']).stdout.decode().strip()
    if not blkid_output:
        raise ValueError("Unable to get blkid info.")

    for device_info in blkid_output.split('\n'):
        device, info = device_info.split(': ')
        info = ' ' + info  # Add space to make regex consistent
        self['_blkid_info'][device] = {}
        self.logger.debug("[%s] Processing blkid line: %s" % (device, info))
        for field in BLKID_FIELDS:
            if match := search(f' {field.upper()}="(.+?)"', info):
                self['_blkid_info'][device][field] = match.group(1)

        if not self['_blkid_info'][device]:
            raise ValueError("[%s] Failed to parse blkid info: %s" % (device, info))

    self.logger.debug("Blkid info: %s" % pretty_print(self['_blkid_info']))


def get_dm_info(self) -> dict:
    """ Populates the device mapper info. """
    if self.get('_dm_info'):
        self.logger.debug("Device mapper info already set.")
        return

    if not Path('/sys/devices/virtual/block').exists():
        self['autodetect_root_dm'] = False
        self.logger.warning("No virtaul block devices found, disabling device mapper autodetection.")
        return

    for dm_device in (Path('/sys/devices/virtual/block').iterdir()):
        if dm_device.name.startswith('dm-'):
            maj, minor = (dm_device / 'dev').read_text().strip().split(':')
            self['_dm_info'][dm_device.name] = {'name': (dm_device / 'dm/name').read_text().strip(),
                                                'major': maj,
                                                'minor': minor,
                                                'holders': [holder.name for holder in (dm_device / 'holders').iterdir()],
                                                'slaves': [slave.name for slave in (dm_device / 'slaves').iterdir()],
                                                'uuid': (dm_device / 'dm/uuid').read_text().strip()}
    if self['_dm_info']:
        self.logger.info("Found device mapper devices: %s" % ', '.join(self['_dm_info'].keys()))
        self.logger.debug("Device mapper info: %s" % pretty_print(self['_dm_info']))
    else:
        self.logger.debug("No device mapper devices found.")


@check_dict('hostonly', value=True, log_level=30, message="Skipping device mapper autodetection, hostonly mode is disabled.")
def _autodetect_dm(self, mountpoint) -> None:
    """ Autodetects device mapper root config. """
    self.logger.debug("Detecting device mapper info for mountpoint: %s", mountpoint)

    source_device = _get_mounts_source_device(self, mountpoint) if not mountpoint.startswith('/dev/') else mountpoint
    root_mount_info = self['_blkid_info'].get(source_device)

    if not root_mount_info:
        root_mount_info = self['_blkid_info'].get(f"/dev/{self._dm_info[str(mountpoint).replace('/dev/', '')]['slaves'][0]}")

    if not root_mount_info:
        raise FileNotFoundError("Unable to find blkdid info for mount point: %s" % mountpoint)

    if not source_device.startswith('/dev/mapper') and not source_device.startswith('/dev/dm-'):
        self.logger.debug("[%s] Mount is not a device mapper mount: %s" % (source_device, root_mount_info))
        return
    self.logger.info("Detected a device mapper mount: %s" % source_device)
    source_device = Path(source_device)
    major, minor = source_device.stat().st_rdev >> 8, source_device.stat().st_rdev & 0xFF
    self.logger.debug("[%s] Major: %s, Minor: %s" % (source_device, major, minor))

    for name, info in self['_dm_info'].items():
        if info['major'] == str(major) and info['minor'] == str(minor):
            mapped_name = name
            break
    else:
        raise RuntimeError("Unable to find device mapper device: %s" % source_device)

    if len(self._dm_info[mapped_name]['slaves']) == 0:
        raise RuntimeError("No slaves found for device mapper device, unknown type: %s" % source_device.name)
    slave_source = self._dm_info[mapped_name]['slaves'][0]

    try:
        dm_mount = self['_blkid_info'][f"/dev/{slave_source}"]
    except KeyError:
        if slave_source in self['_dm_info']:
            dm_mount = self['_blkid_info'][f"/dev/mapper/{self._dm_info[slave_source]['name']}"]
        else:
            raise KeyError("Unable to find blkid info for device mapper slave: %s" % slave_source)
    if source_device.name != self._dm_info[mapped_name]['name'] and source_device.name != mapped_name:
        raise ValueError("Device mapper device name mismatch: %s != %s" % (source_device.name, self._dm_info[mapped_name]['name']))

    self.logger.debug("[%s] Device mapper info: %s" % (source_device.name, self._dm_info[mapped_name]))
    if dm_mount.get('type') == 'crypto_LUKS' or source_device.name in self.get('cryptsetup', {}):
        return autodetect_root_luks(self, source_device, mapped_name, dm_mount)
    elif dm_mount.get('type') == 'LVM2_member':
        return autodetect_root_lvm(self, source_device, mapped_name, dm_mount)
    else:
        raise RuntimeError("Unknown device mapper device type: %s" % dm_mount.get('type'))


@check_dict('autodetect_root_dm', value=True, log_level=10, message="Skipping device mapper autodetection, autodetect_root_dm is not set.")
@check_dict('hostonly', value=True, log_level=30, message="Skipping device mapper autodetection, hostonly mode is disabled.")
def autodetect_root_dm(self) -> None:
    _autodetect_dm(self, '/')


@check_dict('autodetect_root_lvm', value=True, log_level=10, message="Skipping LVM autodetection, autodetect_root_lvm is not set.")
@check_dict('hostonly', value=True, log_level=30, message="Skipping LVM autodetection, hostonly mode is disabled.")
def autodetect_root_lvm(self, mount_loc, mapped_name, lvm_mount) -> None:
    """ Autodetects LVM mounts and sets the lvm config. """
    if 'ugrd.fs.lvm' not in self['modules']:
        self.logger.info("Autodetected LVM mount, enabling the lvm module.")
        self['modules'] = 'ugrd.fs.lvm'

    if uuid := lvm_mount.get('uuid'):
        self.logger.info("[%s] LVM volume uuid: %s" % (mount_loc.name, uuid))
        self['lvm'] = {self._dm_info[mapped_name]['name']: {'uuid': uuid}}
    else:
        raise ValueError("Failed to autodetect LVM volume uuid: %s" % mount_loc.name)

    # Check if the LVM volume is part of a LUKS volume
    for slave in self._dm_info[mapped_name]['slaves']:
        _autodetect_dm(self, '/dev/' + slave)


@check_dict('autodetect_root_luks', value=True, log_level=10, message="Skipping LUKS autodetection, autodetect_root_luks is not set.")
@check_dict('hostonly', value=True, log_level=30, message="Skipping LUKS autodetection, hostonly mode is disabled.")
def autodetect_root_luks(self, mount_loc, mapped_name, luks_mount) -> None:
    """ Autodetects LUKS mounts and sets the cryptsetup config. """
    if 'ugrd.crypto.cryptsetup' not in self['modules']:
        self.logger.info("Autodetected LUKS mount, enabling the cryptsetup module: %s" % mount_loc.name)
        self['modules'] = 'ugrd.crypto.cryptsetup'

    if 'cryptsetup' in self and any(mount_type in self['cryptsetup'].get(self._dm_info[mapped_name]['name'], []) for mount_type in SOURCE_TYPES):
        self.logger.warning("Skipping LUKS autodetection, cryptsetup config already set: %s" % self['cryptsetup'][self._dm_info[mapped_name]['name']])
        return

    if len(self._dm_info[mapped_name]['slaves']) > 1:
        self.logger.error("Device mapper slaves: %s" % self._dm_info[mapped_name]['slaves'])
        raise RuntimeError("Multiple slaves found for device mapper device, unknown type: %s" % mount_loc.name)

    luks_mount = self['_blkid_info'][f"/dev/{self._dm_info[mapped_name]['slaves'][0]}"]
    self.logger.debug("[%s] LUKS mount info: %s" % (mapped_name, luks_mount))
    if luks_mount.get('type') != 'crypto_LUKS':
        if not luks_mount.get('uuid'):  # No uuid will be defined if there are detached headers
            if not self['cryptsetup'][mount_loc.name].get('header_file'):
                raise ValueError("[%s] Unknown LUKS mount type, if using detached headers, specify 'header_file': %s" % (mount_loc.name, luks_mount.get('type')))
        else:  # If there is some uuid and it's not LUKS, that's a problem
            raise RuntimeError("[%s] Unknown device mapper slave type: %s" % (self._dm_info[mapped_name]['slaves'][0], luks_mount.get('type')))

    # Configure cryptsetup based on the LUKS mount
    if uuid := luks_mount.get('uuid'):
        self.logger.info("[%s] LUKS volume uuid: %s" % (mount_loc.name, uuid))
        self['cryptsetup'] = {self._dm_info[mapped_name]['name']: {'uuid': uuid}}
    elif partuuid := luks_mount.get('partuuid'):
        self.logger.info("[%s] LUKS volume partuuid: %s" % (mount_loc.name, partuuid))
        self['cryptsetup'] = {self._dm_info[mapped_name]['name']: {'partuuid': partuuid}}

    self.logger.info("[%s] Configuring cryptsetup for LUKS mount (%s) on: %s\n%s" %
                     (mount_loc.name, self._dm_info[mapped_name]['name'], mapped_name, pretty_print(self['cryptsetup'])))


@check_dict('autodetect_root', value=True, log_level=20, message="Skipping root autodetection, autodetect_root is disabled.")
@check_dict('hostonly', value=True, log_level=30, message="Skipping root autodetection, hostonly mode is disabled.")
def autodetect_root(self) -> None:
    """ Sets self['mounts']['root']'s source based on the host mount. """
    if any(source_type in self['mounts']['root'] for source_type in SOURCE_TYPES):
        self.logger.warning("Root mount source already set: %s", pretty_print(self['mounts']['root']))
        return

    root_mount_info = self['_blkid_info'][_get_mounts_source_device(self, '/')]
    self.logger.debug("Detected root mount info: %s" % root_mount_info)
    mount_info = {'root': {'type': 'auto', 'base_mount': False}}

    if mount_type := root_mount_info.get('type'):  # Attempt to autodetect the root type
        self.logger.info("Autodetected root type: %s" % mount_type)
        mount_info['root']['type'] = mount_type.lower()

    for source_type in SOURCE_TYPES:
        if source := root_mount_info.get(source_type):
            self.logger.info("Autodetected root source: %s=%s" % (source_type, source))
            mount_info['root'][source_type] = source
            break
    else:
        raise ValueError("Failed to autodetect root mount source.")

    self['mounts'] = mount_info


def mount_base(self) -> list[str]:
    """ Generates mount commands for the base mounts. """
    out = [f'einfo "Mounting base mounts, version: {__version__}"']
    for mount in self['mounts'].values():
        if mount.get('base_mount'):
            out += _to_mount_cmd(self, mount, check_mount=True)

    return out


@check_dict('late_mounts', not_empty=True, log_level=20, message="Skipping late mounts, late_mounts is empty.")
def mount_late(self) -> list[str]:
    """ Generates mount commands for the late mounts. """
    target_dir = self['mounts']['root']['destination'] if not self['switch_root_target'] else self['switch_root_target']
    out = [f'einfo "Mounting late mounts at {target_dir}: {" ,".join(self["late_mounts"].keys())}"']
    for mount in self['late_mounts'].values():
        if not str(mount['destination']).startswith(target_dir):
            mount['destination'] = Path(target_dir, str(mount['destination']).removeprefix('/'))
        out += _to_mount_cmd(self, mount, check_mount=True)
    return out


def remake_mountpoints(self) -> list[str]:
    """ Remakes mountpoints, especially useful when mounting over something like /dev. """
    cmds = [f"mkdir --parents {mount['destination']}" for mount in self['mounts'].values() if mount.get('remake_mountpoint')]
    if cmds:
        self['binaries'] += 'mkdir'
        return cmds


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

    out += ["mount -a || _mount_fail 'failed to mount fstab'"]
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
                return str(mount_source)
    if mountpoint.strip().startswith('/dev/dm-'):
        dm_name = self['_dm_info'][mountpoint.strip().removeprefix('/dev/')]['name']
        return _get_mounts_source_device(self, '/dev/mapper/' + dm_name)
    raise FileNotFoundError("Unable to find mount source device for: %s" % mountpoint)


@check_dict('validate', value=True, log_level=30, return_val=True, message="Skipping host mount validation, validation is disabled.")
@check_dict('hostonly', value=True, log_level=30, return_val=True, message="Skipping host mount validation, hostonly mode is enabled.")
def _validate_host_mount(self, mount, destination_path=None) -> bool:
    """ Checks if a defined mount exists on the host. """
    mount_type, mount_val = _get_mount_source_type(self, mount, with_val=True)
    # If a destination path is passed, like for /, use that instead of the mount's destination
    destination_path = mount['destination'] if destination_path is None else destination_path

    # This will raise a FileNotFoundError if the mountpoint doesn't exist
    host_source_dev = _get_mounts_source_device(self, destination_path)

    host_mount_options = _get_mounts_source_options(self, destination_path)
    for option in mount.get('options', []):
        if option == 'ro' and destination_path == '/':
            # Skip the ro option for the root mount
            continue
        if option not in host_mount_options:
            raise ValueError("Host mount options mismatch. Expected: %s, Found: %s" % (mount['options'], host_mount_options))

    if mount_type == 'path' and mount_val != Path(host_source_dev):
        raise ValueError("Host mount path device path does not match config. Expected: %s, Found: %s" % (mount_val, host_source_dev))
    elif mount_type in ['uuid', 'partuuid', 'label']:
        # For uuid, partuuid, and label types, check that the source matches the host mount
        if self['_blkid_info'][host_source_dev][mount_type] != mount_val:
            raise ValueError("Host mount source device mismatch. Expected: %s: %s, Found: %s" % (mount_type, mount_val, host_source_dev))
        self.logger.debug("[%s] Host mount validated: %s" % (destination_path, mount))
        return True
    raise ValueError("[%s] Unable to validate host mount: %s" % (destination_path, mount))


def mount_root(self) -> str:
    """
    Mounts the root partition to $MOUNTS_ROOT_TARGET.
    Warns if the root partition isn't found on the current system.
    """
    _validate_host_mount(self, self['mounts']['root'], '/')
    # Check if the root mount is already mounted
    return ['if grep -qs "$(cat /run/MOUNTS_ROOT_TARGET)" /proc/mounts; then',
            '    ewarn "Root mount already exists, unmounting: $(cat /run/MOUNTS_ROOT_TARGET)"',
            '    umount "$(cat /run/MOUNTS_ROOT_TARGET)"',
            'fi',
            '''einfo "Mounting '$(cat /run/MOUNTS_ROOT_SOURCE)' ($(cat /run/MOUNTS_ROOT_TYPE)) to '$(cat /run/MOUNTS_ROOT_TARGET)' with options: $(cat /run/MOUNTS_ROOT_OPTIONS)"''',
            'mount "$(cat /run/MOUNTS_ROOT_SOURCE)" -t "$(cat /run/MOUNTS_ROOT_TYPE)" "$(cat /run/MOUNTS_ROOT_TARGET)" -o "$(cat /run/MOUNTS_ROOT_OPTIONS)"']


def export_mount_info(self) -> None:
    """ Exports mount info based on the config to /run/MOUNTS_ROOT_{option} """
    return [f'echo -n "{self["mounts"]["root"]["destination"]}" > "/run/MOUNTS_ROOT_TARGET"',
            f'echo -n "{_get_mount_str(self, self["mounts"]["root"])}" > "/run/MOUNTS_ROOT_SOURCE"',
            f'echo -n "{self["mounts"]["root"].get("type", "auto")}" > "/run/MOUNTS_ROOT_TYPE"',
            f'''echo -n "{','.join(self["mounts"]["root"]["options"])}" > "/run/MOUNTS_ROOT_OPTIONS"''']


def _mount_fail(self) -> list[str]:
    """ Generates init lines to run if the mount fails. """
    return ['if [ -n "$1" ]; then',
            '    ewarn "Mount failed: $1"',
            'else',
            '    ewarn "Mount failed"',
            'fi',
            r'echo -e "\n\n\nPress enter to display debug info.\n\n\n"',
            'read -sr',
            r'einfo -e "\nLoaded modules:"',
            'cat /proc/modules',
            r'einfo -e "\nBlock devices:"',
            'blkid',
            r'einfo -e "\nMounts:"',
            'mount',
            r'echo -e "\n\n\nPress enter to restart init.\n\n\n"',
            'read -sr',
            'if [ "$$" -eq 1 ]; then',
            '    einfo "Restarting init"',
            '    exec /init ; exit',
            'else',
            '    ewarn "PID is not 1, exiting: $$"',
            '    exit',
            'fi']


