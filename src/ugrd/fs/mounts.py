__author__ = 'desultory'
__version__ = '4.11.2'

from pathlib import Path
from zenlib.util import contains, pretty_print

BLKID_FIELDS = ['uuid', 'partuuid', 'label', 'type']
SOURCE_TYPES = ['uuid', 'partuuid', 'label', 'path']
MOUNT_PARAMETERS = ['destination', 'source', 'type', 'options', 'no_validate', 'base_mount', *SOURCE_TYPES]


@contains('validate', "Skipping mount validation, validation is disabled.", log_level=30)
def _validate_mount_config(self, mount_name: str, mount_config) -> None:
    """ Validate the mount config. """
    if mount_config.get('no_validate'):
        return self.logger.warning("Skipping mount validation: %s" % mount_name)

    for source_type in SOURCE_TYPES:
        if source_type in mount_config:
            self.logger.debug("[%s] Validated source type: %s" % (mount_name, mount_config))
            break
    else:  # If no source type is found, raise an error, unless it's the root mount
        if source_type not in mount_config and mount_name != 'root':
            raise ValueError("[%s] No source type found in mount: %s" % (mount_name, mount_config))

    for parameter, value in mount_config.copy().items():
        self.logger.debug("[%s] Validating parameter: %s" % (mount_name, parameter))
        if parameter == 'source' and isinstance(value, dict):
            self.logger.warning("source dict is deprecated, please define the source type directly.")
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
        elif mount_type == 'nilfs2':
            self['binaries'] = 'mount.nilfs2'
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
    self.data['mount_timeout'] = timeout


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


def _to_mount_cmd(self, mount: dict) -> str:
    """ Prints the object as a mount command. """
    out = [f"if ! grep -qs {mount['destination']} /proc/mounts; then"]

    mount_command = f"mount {_get_mount_str(self, mount)} {mount['destination']}"
    if options := mount.get('options'):
        mount_command += f" --options {','.join(options)}"
    if mount_type := mount.get('type'):
        mount_command += f" -t {mount_type}"

    mount_command += f" || rd_fail 'Failed to mount: {mount['destination']}'"

    out += [f"    {mount_command}",
            'else',
            f"    ewarn 'Mount already exists, skipping: {mount['destination']}'",
            'fi']

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
            except KeyError:
                self.logger.warning("System mount info:\n%s" % pretty_print(self['_mounts']))
                raise ValueError("[%s] Failed to add fstab entry for: %s" % (mount_class, mount_name))

    if len(fstab_info) > 1:
        self._write(filename, fstab_info)
    else:
        self.logger.debug("[%s] No fstab entries generated for mounts: %s" % (mount_class, ', '.join(self[mount_class].keys())))


def get_mounts_info(self) -> None:
    """ Gets the mount info for all devices. """
    with open('/proc/mounts', 'r') as mounts:
        for line in mounts:
            device, mountpoint, fstype, options, _, _ = line.split()
            self['_mounts'][mountpoint] = {'device': device, 'fstype': fstype, 'options': options.split(',')}


def get_blkid_info(self, device=None) -> str:
    """
    Gets the blkid info for all devices if no device is passed.
    Gets the blkid info for the passed device if a device is passed.
    The info is stored in self['_blkid_info'].
    """
    from re import search
    if device:
        blkid_output = self._run(['blkid', device]).stdout.decode().strip()
    else:
        blkid_output = self._run(['blkid']).stdout.decode().strip()

    if not blkid_output:
        raise ValueError("Unable to get blkid info.")

    for device_info in blkid_output.split('\n'):
        dev, info = device_info.split(': ')
        info = ' ' + info  # Add space to make regex consistent
        self['_blkid_info'][dev] = {}
        self.logger.debug("[%s] Processing blkid line: %s" % (dev, info))
        for field in BLKID_FIELDS:
            if match := search(f' {field.upper()}="(.+?)"', info):
                self['_blkid_info'][dev][field] = match.group(1)

    if device and not self['_blkid_info'][device]:
        raise ValueError("[%s] Failed to parse blkid info: %s" % (device, info))

    self.logger.debug("Blkid info: %s" % pretty_print(self['_blkid_info']))


@contains('init_target', 'init_target must be set', raise_exception=True)
@contains('autodetect_init_mount', 'Skipping init mount autodetection, autodetect_init_mount is disabled.', log_level=30)
@contains('hostonly', 'Skipping init mount autodetection, hostonly mode is disabled.', log_level=30)
def autodetect_init_mount(self, parent=None) -> None:
    """ Checks the parent directories of init_target, if the path is a mountpoint, add it to late_mounts. """
    if not parent:
        parent = self['init_target'].parent
    if parent == Path('/'):
        return
    if str(parent) in self['_mounts']:
        self.logger.info("Detected init mount: %s" % parent)
        mount_name = str(parent).removeprefix('/')
        mount_dest = str(parent)
        mount_device = self['_mounts'][str(parent)]['device']
        mount_type = self['_mounts'][str(parent)]['fstype']
        mount_options = self['_mounts'][str(parent)]['options']
        blkid_info = self['_blkid_info'][mount_device]
        mount_source_type, mount_source = _get_mount_source_type(self, blkid_info, with_val=True)
        self['late_mounts'][mount_name] = {'destination': mount_dest,
                                           mount_source_type: mount_source,
                                           'type': mount_type,
                                           'options': mount_options}
    autodetect_init_mount(self, parent.parent)


def get_dm_info(self) -> dict:
    """
    Populates the device mapper info.
    Disables device mapper autodetection if no virtual block devices are found.
    """
    if self.get('_dm_info'):
        self.logger.debug("Device mapper info already set.")
        return

    if not Path('/sys/devices/virtual/block').exists():
        self['autodetect_root_dm'] = False
        self.logger.warning("No virtual block devices found, disabling device mapper autodetection.")
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


def _get_device_id(device: str) -> str:
    """ Gets the device id from the device path. """
    return Path(device).stat().st_rdev >> 8, Path(device).stat().st_rdev & 0xFF


@contains('hostonly', "Skipping device mapper autodetection, hostonly mode is disabled.", log_level=30)
def _autodetect_dm(self, mountpoint) -> None:
    """
    Autodetects device mapper config given a device.
    If no device is passed, it will attempt to autodetect based on the mountpoint.
    """
    if mountpoint in self['_mounts']:
        source_device = self['_mounts'][mountpoint]['device']
    else:
        source_device = "/dev/mapper/" + self['_dm_info'][mountpoint.split('/')[-1]]['name']

    if not source_device or source_device not in self['_blkid_info']:
        raise FileNotFoundError("[%s] No blkdid info for dm device: %s" % (mountpoint, source_device))

    if not source_device.startswith('/dev/mapper') and not source_device.startswith('/dev/dm-'):
        self.logger.debug("Mount is not a device mapper mount: %s" % source_device)
        return

    self.logger.info("Detected a device mapper mount: %s" % source_device)
    source_device = Path(source_device)
    major, minor = _get_device_id(source_device)
    self.logger.debug("[%s] Major: %s, Minor: %s" % (source_device, major, minor))

    for name, info in self['_dm_info'].items():
        if info['major'] == str(major) and info['minor'] == str(minor):
            dm_num = name
            break
    else:
        raise RuntimeError("[%s] Unable to find device mapper device with maj: %s min: %s" % (source_device, major, minor))

    if len(self._dm_info[dm_num]['slaves']) == 0:
        raise RuntimeError("No slaves found for device mapper device, unknown type: %s" % source_device.name)
    slave_source = self._dm_info[dm_num]['slaves'][0]

    try:
        dm_info = self['_blkid_info'][f"/dev/{slave_source}"]
    except KeyError:
        if slave_source in self['_dm_info']:
            dm_info = self['_blkid_info'][f"/dev/mapper/{self._dm_info[slave_source]['name']}"]
        else:
            raise KeyError("Unable to find blkid info for device mapper slave: %s" % slave_source)
    if source_device.name != self._dm_info[dm_num]['name'] and source_device.name != dm_num:
        raise ValueError("Device mapper device name mismatch: %s != %s" % (source_device.name, self._dm_info[dm_num]['name']))

    self.logger.debug("[%s] Device mapper info: %s" % (source_device.name, self._dm_info[dm_num]))
    if dm_info.get('type') == 'crypto_LUKS' or source_device.name in self.get('cryptsetup', {}):
        return autodetect_luks(self, source_device, dm_num, dm_info)
    elif dm_info.get('type') == 'LVM2_member':
        return autodetect_root_lvm(self, source_device, dm_num, dm_info)
    else:
        raise RuntimeError("Unknown device mapper device type: %s" % dm_info.get('type'))


@contains('autodetect_root_dm', "Skipping device mapper autodetection, autodetect_root_dm is disabled.", log_level=30)
@contains('hostonly', "Skipping device mapper autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_root_dm(self) -> None:
    _autodetect_dm(self, '/')


@contains('autodetect_root_lvm', "Skipping LVM autodetection, autodetect_root_lvm is disabled.", log_level=20)
@contains('hostonly', "Skipping LVM autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_root_lvm(self, mount_loc, dm_num, dm_info) -> None:
    """ Autodetects LVM mounts and sets the lvm config. """
    if 'ugrd.fs.lvm' not in self['modules']:
        self.logger.info("Autodetected LVM mount, enabling the lvm module.")
        self['modules'] = 'ugrd.fs.lvm'

    if uuid := dm_info.get('uuid'):
        self.logger.info("[%s] LVM volume uuid: %s" % (mount_loc.name, uuid))
        self['lvm'] = {self._dm_info[dm_num]['name']: {'uuid': uuid}}
    else:
        raise ValueError("Failed to autodetect LVM volume uuid: %s" % mount_loc.name)

    # Check if the LVM volume is part of a LUKS volume
    for slave in self._dm_info[dm_num]['slaves']:
        try:
            _autodetect_dm(self, '/dev/' + slave)
        except KeyError:
            self.logger.debug("LVM slave does not appear to be a DM device: %s" % slave)


@contains('autodetect_root_luks', "Skipping LUKS autodetection, autodetect_root_luks is disabled.", log_level=30)
@contains('hostonly', "Skipping LUKS autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_luks(self, mount_loc, dm_num, dm_info) -> None:
    """ Autodetects LUKS mounts and sets the cryptsetup config. """
    if 'ugrd.crypto.cryptsetup' not in self['modules']:
        self.logger.info("Autodetected LUKS mount, enabling the cryptsetup module: %s" % mount_loc.name)
        self['modules'] = 'ugrd.crypto.cryptsetup'

    if 'cryptsetup' in self and any(mount_type in self['cryptsetup'].get(self._dm_info[dm_num]['name'], []) for mount_type in SOURCE_TYPES):
        self.logger.warning("Skipping LUKS autodetection, cryptsetup config already set: %s" % self['cryptsetup'][self._dm_info[dm_num]['name']])
        return

    if len(self._dm_info[dm_num]['slaves']) > 1:
        self.logger.error("Device mapper slaves: %s" % self._dm_info[dm_num]['slaves'])
        raise RuntimeError("Multiple slaves found for device mapper device, unknown type: %s" % mount_loc.name)

    dm_type = dm_info.get('type')
    if dm_type != 'crypto_LUKS':
        if not dm_info.get('uuid'):  # No uuid will be defined if there are detached headers
            if not self['cryptsetup'][mount_loc.name].get('header_file'):
                raise ValueError("[%s] Unknown LUKS mount type: %s" % (mount_loc.name, dm_type))
        else:  # If there is some uuid and it's not LUKS, that's a problem
            raise RuntimeError("[%s] Unknown device mapper slave type: %s" % (self._dm_info[dm_num]['slaves'][0], dm_type))

    # Configure cryptsetup based on the LUKS mount
    if uuid := dm_info.get('uuid'):
        self.logger.info("[%s] LUKS volume uuid: %s" % (mount_loc.name, uuid))
        self['cryptsetup'] = {self._dm_info[dm_num]['name']: {'uuid': uuid}}
    elif partuuid := dm_info.get('partuuid'):
        self.logger.info("[%s] LUKS volume partuuid: %s" % (mount_loc.name, partuuid))
        self['cryptsetup'] = {self._dm_info[dm_num]['name']: {'partuuid': partuuid}}

    self.logger.info("[%s] Configuring cryptsetup for LUKS mount (%s) on: %s\n%s" %
                     (mount_loc.name, self._dm_info[dm_num]['name'], dm_num, pretty_print(self['cryptsetup'])))


def _resolve_root_dev(self) -> None:
    """
    Resolves the root device, if possible.
    Useful for cases where the device in blkid differs from the device in /proc/mounts.
    """
    major, minor = _get_device_id(self['_mounts']['/']['device'])
    for device in self['_blkid_info']:
        check_major, check_minor = _get_device_id(device)
        if (major, minor) == (check_major, check_minor):
            self.logger.info("Resolved root device: %s -> %s" % (self['_mounts']['/']['device'], device))
            return device
    self.logger.warning("Failed to resolve root device: %s" % self['_mounts']['/']['device'])
    return self['_mounts']['/']['device']


@contains('autodetect_root', "Skipping root autodetection, autodetect_root is disabled.", log_level=30)
@contains('hostonly', "Skipping root autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_root(self) -> None:
    """ Sets self['mounts']['root']'s source based on the host mount. """
    if any(source_type in self['mounts']['root'] for source_type in SOURCE_TYPES):
        self.logger.warning("Root mount source already set: %s", pretty_print(self['mounts']['root']))
        return

    # Sometimes the root device listed in '/proc/mounts' differs from the blkid info
    root_dev = self['_mounts']['/']['device']
    if self['resolve_root_dev']:
        root_dev = _resolve_root_dev(self)
    if root_dev not in self['_blkid_info']:
        get_blkid_info(self, root_dev)

    root_mount_info = self['_blkid_info'][root_dev]
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
    """
    Generates mount commands for the base mounts.
    Must be run before variables are used, as it creates the /run/vars directory.
    """
    out = []
    for mount in self['mounts'].values():
        if mount.get('base_mount'):
            out += _to_mount_cmd(self, mount)
    out += ['mkdir -p /run/vars',
            f'einfo "Mounted base mounts, version: {__version__}"']
    return out


@contains('late_mounts', "Skipping late mounts, late_mounts is empty.")
def mount_late(self) -> list[str]:
    """ Generates mount commands for the late mounts. """
    target_dir = str(self['mounts']['root']['destination'])
    out = [f'einfo "Mounting late mounts at {target_dir}: {" ,".join(self["late_mounts"].keys())}"']
    for mount in self['late_mounts'].values():
        if not str(mount['destination']).startswith(target_dir):
            mount['destination'] = Path(target_dir, str(mount['destination']).removeprefix('/'))
        out += _to_mount_cmd(self, mount)
    return out


def mount_fstab(self) -> list[str]:
    """
    Generates the init function for mounting the fstab.
    If a mount_timeout is set, sets the default rootdelay.
    If a mount_wait is set, enables rootwait.
    mount_retries sets the number of times to retry the mount (for unattended booting).
    """
    out = []
    if timeout := self.get('mount_timeout'):  # Set the timeout, using the defined timeout as the default
        out.append(f'timeout=$(readvar rootdelay {timeout})')
    else:
        out.append('timeout=$(readvar rootdelay)')

    if rootwait := self.get('mount_wait'):  # Set the rootwait bool, using the defined rootwait as the default
        out.append(f'rootwait=$(readvar rootwait {int(rootwait)})')
    else:
        out.append('rootwait=$(readvar rootwait)')

    out += ['if [ -z "$timeout" ]; then',  # If timeout is not set, prompt the user -
            '    if [ "$rootwait" == "1" ]; then',  # only if rootwait is set to 1
            '        prompt_user "Press enter once devices have settled."',
            '    fi',
            'else',  # If timeout is set, prompt the user with a timeout
            '    prompt_user "Press enter once devices have settled. [${timeout}s]" "$timeout"',
            'fi',
            f'retry {self["mount_retries"]} "${{timeout:-1}}" mount -a || rd_fail "Failed to mount all filesystems."']

    return out


@contains('validate', "Skipping host mount validation, validation is disabled.", log_level=30)
def _validate_host_mount(self, mount, destination_path=None) -> bool:
    """ Checks if a defined mount exists on the host. """
    if mount.get('no_validate'):
        return self.logger.warning("Skipping host mount validation for config:\n%s" % pretty_print(mount))

    mount_type, mount_val = _get_mount_source_type(self, mount, with_val=True)
    # If a destination path is passed, like for /, use that instead of the mount's destination
    destination_path = str(mount['destination']) if destination_path is None else destination_path

    # Using the mount path, get relevant hsot mount info
    host_source_dev = self['_mounts'][destination_path]['device']
    if destination_path == '/' and self['resolve_root_dev']:
        host_source_dev = _resolve_root_dev(self)
    host_mount_options = self['_mounts'][destination_path]['options']
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
    return ['if grep -qs "$(readvar MOUNTS_ROOT_TARGET)" /proc/mounts; then',
            '    ewarn "Root mount already exists, unmounting: $(readvar MOUNTS_ROOT_TARGET)"',
            '    umount "$(readvar MOUNTS_ROOT_TARGET)"',
            'fi',
            '''einfo "Mounting '$(readvar MOUNTS_ROOT_SOURCE)' ($(readvar MOUNTS_ROOT_TYPE)) to '$(readvar MOUNTS_ROOT_TARGET)' with options: $(readvar MOUNTS_ROOT_OPTIONS)"''',
            f'retry {self["mount_retries"]} {self["mount_timeout"] or 1} mount "$(readvar MOUNTS_ROOT_SOURCE)" -t "$(readvar MOUNTS_ROOT_TYPE)" "$(readvar MOUNTS_ROOT_TARGET)" -o "$(readvar MOUNTS_ROOT_OPTIONS)"']


def export_mount_info(self) -> None:
    """ Exports mount info based on the config to /run/MOUNTS_ROOT_{option} """
    self['exports']['MOUNTS_ROOT_SOURCE'] = _get_mount_str(self, self['mounts']['root'])
    self['exports']['MOUNTS_ROOT_TYPE'] = self['mounts']['root'].get('type', 'auto')
    self['exports']['MOUNTS_ROOT_OPTIONS'] = ','.join(self['mounts']['root']['options'])


def export_root_target(self) -> None:
    """ Exports the root target path to /run/MOUNTS_ROOT_TARGET """
    self['exports']['MOUNTS_ROOT_TARGET'] = self['mounts']['root']['destination']
