__author__ = 'desultory'
__version__ = '1.1.1'

from pathlib import Path


MOUNT_PARAMETERS = ['destination', 'source', 'type', 'options', 'base_mount', 'skip_unmount', 'remake_mountpoint']


def _process_mounts_multi(self, mount_name, mount_config):
    """
    Processes the passed mounts into fstab mount objects
    under 'mounts'
    """
    if mount_name in self['mounts']:
        self.logger.info("Updating mount: %s" % mount_name)
        self.logger.debug("[%s] Updating mount with: %s" % (mount_name, mount_config))
        if 'options' in self['mounts'][mount_name] and 'options' in mount_config:
            self.logger.debug("Merging options: %s" % mount_config['options'])
            self['mounts'][mount_name]['options'] = self['mounts'][mount_name]['options'] | set(mount_config['options'])
            mount_config.pop('options')
        mount_config = dict(self['mounts'][mount_name], **mount_config)

    for parameter in mount_config:
        if parameter not in MOUNT_PARAMETERS:
            raise ValueError("Invalid parameter in mount: %s" % parameter)

    mount_config['destination'] = Path(mount_config.get('destination', mount_name))
    mount_config['base_mount'] = mount_config.get('base_mount', False)
    mount_config['options'] = set(mount_config.get('options', ''))

    if mount_type := mount_config.get('type'):
        if mount_type == 'vfat':
            self['_kmod_depend'] = 'vfat'
        elif mount_type == 'btrfs':
            if 'ugrd.fs.btrfs' not in self['modules']:
                self.logger.info("Auto-enabling btrfs module")
                self['modules'] = 'ugrd.fs.btrfs'

    self['mounts'][mount_name] = mount_config

    self.logger.debug("[%s] Added mount: %s" % (mount_name, mount_config))

    self['paths'].append(mount_config['destination'])


def _get_mount_source(self, mount, pad=False):
    """
    returns the mount source string based on the config
    uses NAME= format so it works in both the fstab and mount command
    """
    source = mount['source']
    pad_size = 44

    out_str = ''
    if isinstance(source, dict):
        if 'uuid' in source:
            out_str = f"UUID={source['uuid']}"
        elif 'partuuid' in source:
            out_str = f"PARTUUID={source['partuuid']}"
        elif 'label' in source:
            out_str = f"LABEL={source['label']}"
        else:
            raise ValueError("Unable to process source entry: %s" % repr(source))
    else:
        out_str = source

    if pad:
        if len(out_str) > pad_size:
            pad_size = len(out_str) + 1
        out_str = out_str.ljust(pad_size, ' ')

    return out_str


def _to_mount_cmd(self, mount):
    """
    Prints the object as a mount command
    """
    out_str = f"mount {_get_mount_source(self, mount)} {mount['destination']}"

    if options := mount.get('options'):
        out_str += f" --options {','.join(options)}"

    if mount_type := mount.get('type'):
        out_str += f" --types {mount_type}"

    return out_str


def _to_fstab_entry(self, mount):
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


def generate_fstab(self):
    """
    Generates the fstab from the mounts
    """
    fstab_info = [f"# UGRD Filesystem module v{__version__}"]

    for mount_name, mount_info in self.config_dict['mounts'].items():
        if not mount_info.get('base_mount'):
            self.logger.debug("Adding fstab entry for: %s" % mount_name)
            fstab_info.append(_to_fstab_entry(self, mount_info))

    self._write('/etc/fstab/', fstab_info)


def mount_base(self):
    """
    Generates mount commands for the base mounts
    """
    return [_to_mount_cmd(self, mount) for mount in self.config_dict['mounts'].values() if mount.get('base_mount')]


def remake_mountpoints(self):
    """
    Remakes mountpoints, especially useful when mounting over something like /dev
    """
    return [f"mkdir --parents {mount['destination']}" for mount in self.config_dict['mounts'].values() if mount.get('remake_mountpoint')]


def mount_fstab(self):
    """
    Generates the init line for mounting the fstab
    """
    out = []

    # Only wait if root_wait is specified
    if self.config_dict.get('mount_wait', False):
        out += [r'echo -e "\n\n\nPress enter once devices have settled.\n\n\n"']
        if self.config_dict.get('mount_timeout', False):
            out += [f"read -sr -t {self.config_dict['mount_timeout']}"]
        else:
            out += ["read -sr"]

    out += ["mount -a || (echo 'Failed to mount fstab. Please ensure mounts are made and then exit.' && bash)"]

    return out


def _get_mounts_source(self, mount):
    """
    Returns the source device of a mountpoint on /proc/mounts
    """
    self.logger.debug("Getting mount source for: %s" % mount)
    # Add space padding to the mount name
    mount = mount if mount.startswith(' ') else ' ' + mount
    mount = mount if mount.endswith(' ') else mount + ' '

    with open('/proc/mounts', 'r') as mounts:
        for line in mounts:
            if mount in line:
                # If the mount is found, return the source
                # Resolve the path as it may be a symlink
                mount_source = Path(line.split()[0]).resolve()
                self.logger.debug("Found mount source: %s" % mount_source)
                return mount_source
    self.logger.warning("Unable to find mount source for: %s" % mount)


def _get_lsblk_info(self, mount, output_fields="NAME,UUID,PARTUUID,LABEL"):
    """
    Gets the lsblk info for a mountpoint
    """
    from json import loads, JSONDecodeError

    self.logger.debug("Getting lsblk info for: %s" % mount)

    mount_info = self._run(['lsblk', '--json', '--output', output_fields, str(mount)])
    try:
        mount_info = loads(mount_info.stdout)
    except JSONDecodeError:
        self.logger.warning("Unable to parse lsblk info for: %s" % mount)
        return None

    self.logger.debug("Found lsblk info: %s" % mount_info)
    return mount_info

def mount_root(self):
    """
    Mounts the root partition.
    Warns if the root partition isn't found on the current system.
    """
#    root_source = self.config_dict['mounts']['root']['source']
    host_root_dev = _get_mounts_source(self, '/')
    lsblk_info = _get_lsblk_info(self, host_root_dev)

    root_path = self.config_dict['mounts']['root']['destination']

    return [f"mount {root_path} || (echo 'Failed to mount root partition' && bash)"]


def clean_mounts(self):
    """
    Generates init lines to unmount all mounts
    """
    return [f"umount {mount['destination']}" for mount in self.config_dict['mounts'].values() if not mount.get('skip_unmount')]


