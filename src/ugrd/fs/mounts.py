__author__ = 'desultory'
__version__ = '1.7.3'

from pathlib import Path


MOUNT_PARAMETERS = ['destination', 'source', 'type', 'options', 'base_mount', 'skip_unmount', 'remake_mountpoint']
SOURCE_TYPES = ['uuid', 'partuuid', 'label']


def _process_mounts_multi(self, mount_name: str, mount_config) -> None:
    """
    Processes the passed mount config.
    Updates the mount if it already exists.
    """
    # If the mount already exists, merge the options and update it
    if mount_name in self['mounts']:
        self.logger.info("Updating mount: %s" % mount_name)
        self.logger.debug("[%s] Updating mount with: %s" % (mount_name, mount_config))
        if 'options' in self['mounts'][mount_name] and 'options' in mount_config:
            self.logger.debug("Merging options: %s" % mount_config['options'])
            self['mounts'][mount_name]['options'] = self['mounts'][mount_name]['options'] | set(mount_config['options'])
            mount_config.pop('options')
        mount_config = dict(self['mounts'][mount_name], **mount_config)

    # Validate the mount config
    for parameter, value in mount_config.items():
        self.logger.debug("[%s] Validating parameter: %s" % (mount_name, parameter))
        if parameter == 'source' and isinstance(value, dict):
            # Break if the source type is valid
            for source_type in SOURCE_TYPES:
                if source_type in value:
                    break
            else:
                self.logger.info("Valid source types: %s" % SOURCE_TYPES)
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

    # Set defaults
    mount_config['destination'] = Path(mount_config.get('destination', mount_name))
    if not mount_config['destination'].is_absolute():
        mount_config['destination'] = '/' / mount_config['destination']
    mount_config['base_mount'] = mount_config.get('base_mount', False)
    mount_config['options'] = set(mount_config.get('options', ''))

    # Check if the mount exists on the host if it's not a base mount or the root mount
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


def _to_mount_cmd(self, mount: dict) -> str:
    """ Prints the object as a mount command. """
    out_str = f"mount {_get_mount_source(self, mount)} {mount['destination']}"

    # I could probably add subvol info here, but I want to keep fs specific stuff out of the core
    if options := mount.get('options'):
        out_str += f" --options {','.join(options)}"

    if mount_type := mount.get('type'):
        out_str += f" --types {mount_type}"

    return out_str


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


def autodetect_root(self) -> None:
    """ Sets self['mounts']['root']['source'] based on the host mount. """
    if not self['autodetect_root']:
        self.logger.debug("Skipping root autodetection, autodetect_root is not set.")
        return

    if source := self['mounts']['root'].get('source'):
        self.logger.warning("Skipping root autodetection, source is already set to: %s" % source)
        return

    if not self['hostonly']:
        self.logger.warning("Skipping root autodetection, hostonly is not set.")
        return

    root_mount_info = _get_blkid_info(self, _get_mounts_source_device(self, '/'))
    self.logger.debug("Detected root mount info: %s" % root_mount_info)

    mount_data = root_mount_info.partition(':')[2].strip().split(' ')
    root_dict = {key: value.strip('"') for key, value in (entry.split('=') for entry in mount_data)}

    mount_info = {'root': {'type': 'auto', 'base_mount': False}}

    if mount_type := root_dict.get('TYPE'):
        self.logger.info("Autodetected root type: %s" % mount_type)
        mount_info['root']['type'] = mount_type.lower()

    if label := root_dict.get('LABEL'):
        self.logger.info("Autodetected root label: %s" % label)
        mount_info['root']['source'] = {'label': label}
    elif uuid := root_dict.get('UUID'):
        self.logger.info("Autodetected root uuid: %s" % uuid)
        mount_info['root']['source'] = {'uuid': uuid}
    else:
        raise ValueError("Failed to autodetect root mount source.")

    self['mounts'] = mount_info


def mount_base(self) -> list[str]:
    """ Generates mount commands for the base mounts. """
    return [_to_mount_cmd(self, mount) for mount in self['mounts'].values() if mount.get('base_mount')]


def remake_mountpoints(self) -> list[str]:
    """ Remakes mountpoints, especially useful when mounting over something like /dev. """
    return [f"mkdir --parents {mount['destination']}" for mount in self['mounts'].values() if mount.get('remake_mountpoint')]


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


def _get_mounts_source_device(self, mountpoint: str) -> Path:
    """ Returns the source device of a mountpoint on /proc/mounts. """
    mountpoint = str(mountpoint)

    self.logger.debug("Getting source device path for: %s" % mountpoint)
    # Add space padding to the mountpoint
    mountpoint = mountpoint if mountpoint.startswith(' ') else ' ' + mountpoint
    mountpoint = mountpoint if mountpoint.endswith(' ') else mountpoint + ' '

    with open('/proc/mounts', 'r') as mounts:
        for line in mounts:
            if mountpoint in line:
                # If the mountpoint is found, return the source
                # Resolve the path as it may be a symlink
                mount_source = Path(line.split()[0]).resolve()
                self.logger.debug("Found mount source: %s" % mount_source)
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

    mount_info = cmd.stdout.decode().strip()

    if not mount_info:
        self.logger.warning("Unable to find blkid info for: %s" % device)
        return None

    self.logger.debug("Found blkid info: %s" % mount_info)
    return mount_info


def _validate_host_mount(self, mount, destination_path=None) -> bool:
    """ Checks if a defined mount exists on the host. """
    if not self.validate:
        self.logger.debug("Skipping host mount check as validation is disabled.")
        return True

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
                search_str = f'{key.upper()}="{value}"'
                if value in blkid_info:
                    self.logger.debug("Found host device match: %s" % search_str)
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
            'clean_mounts',
            'if [ "$$" -eq 1 ]; then',
            '    echo "Restarting init"',
            '    exec /init',
            'else',
            '    echo "PID is not 1, exiting: $$"',
            '    exit',
            'fi']


