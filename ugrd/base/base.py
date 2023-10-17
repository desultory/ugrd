__author__ = 'desultory'
__version__ = '0.4.0'

from pathlib import Path


def generate_fstab(self):
    """
    Generates the fstab from the mounts
    """
    fstab_path = self.config_dict['out_dir'] / 'etc/fstab'

    with open(fstab_path, 'w') as fstab_file:
        for mount_name, mount_info in self.config_dict['mounts'].items():
            fstab_file.write(f"{mount_info.to_fstab_entry()}\n")


def mount_base(self):
    """
    Generates mount commands for the base mounts
    """
    return [mount.to_mount_cmd() for mount in self.config_dict['mounts'].values() if mount.base_mount]


def generate_nodes(self):
    """
    Generates specified device nodes
    """
    from os import makedev, mknod
    from stat import S_IFCHR

    for node, config in self.config_dict['dev_nodes'].items():
        node_path_abs = Path(config['path'])

        node_path = self.config_dict['out_dir'] / node_path_abs.relative_to(node_path_abs.anchor)
        node_mode = S_IFCHR | config['mode']

        mknod(node_path, mode=node_mode, device=makedev(config['major'], config['minor']))
        self.logger.info("Created device node %s at path: %s" % (node, node_path))


def switch_root(self):
    """
    Should be the final statement, switches root
    """
    return ["exec switch_root /mnt/root /sbin/init"]


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


def mount_root(self):
    """
    Mounts the root partition
    """
    mount_info = self.config_dict['root_mount']

    if 'destination' in mount_info:
        raise ValueError("Root mount should not have a destination specified")
    else:
        mount_info['destination'] = '/mnt/root'

    if 'options' not in mount_info:
        mount_info['options'] = 'ro'

    root_mount = Mount(**mount_info)

    mount_str = root_mount.to_mount_cmd() + " || (echo 'Failed to mount root partition' && bash)"

    return [mount_str]


def clean_mounts(self):
    """
    Generates init lines to unmount all mounts
    """
    return [f"umount /{mount}" for mount in self.config_dict['mounts']]


def _process_file_owner(self, owner):
    """
    Processes the passed file owner into a uid
    """
    from pwd import getpwnam

    if isinstance(owner, str):
        try:
            self.logger.debug("Processing file owner: %s" % owner)
            self['_file_owner_uid'] = getpwnam(owner).pw_uid
            self.logger.info("Detected file owner uid: %s" % self['_file_owner_uid'])
        except KeyError as e:
            self.logger.error("Unable to process file owner: %s" % owner)
            self.logger.error(e)
    elif isinstance(owner, int):
        self['_file_owner_uid'] = owner
        self.logger.info("Set file owner uid: %s" % self['_file_owner_uid'])
    else:
        self.logger.error("Unable to process file owner: %s" % owner)
        raise ValueError("Invalid type passed for file owner: %s" % type(owner))


def _process_mounts_multi(self, key, mount_config):
    """
    Processes the passed mounts into fstab mount objects
    under 'fstab_mounts'
    """
    if 'destination' not in mount_config:
        mount_config['destination'] = f"/{key}"  # prepend a slash

    try:
        self['mounts'][key] = Mount(**mount_config)
        self['paths'].append(mount_config['destination'])
    except ValueError as e:
        self.logger.error("Unable to process mount: %s" % key)
        self.logger.error(e)


class Mount:
    """
    Abstracts a linux mount.
    """
    __version__ = '0.3.0'

    parameters = {'destination': True,
                  'source': True,
                  'type': False,
                  'options': False}

    def __init__(self, *args, **kwargs):
        for parameter in self.parameters:
            if kwargs.get(parameter):
                # Validate if ther is a validator function
                if hasattr(self, f'validate_{parameter}') and not getattr(self, f'validate_{parameter}')(kwargs.get(parameter)):
                    raise ValueError("Invalid value passed for parameter: %s" % parameter)
                setattr(self, parameter, kwargs.pop(parameter))
            elif self.parameters[parameter]:
                raise ValueError("Required parameter was not passed: %s" % parameter)

        self.base_mount = kwargs.pop('base_mount', False)

    def validate_destination(self, destination):
        """
        Validates the destination
        """
        if not destination.startswith('/'):
            return False
        return True

    def get_source(self, pad=False):
        """
        returns the mount source string based on the config
        """
        out_str = ''
        if isinstance(self.source, dict):
            if 'uuid' in self.source:
                out_str = f"UUID={self.source['uuid']}"
            elif 'label' in self.source:
                out_str = f"LABEL={self.source['label']}"
            else:
                raise ValueError("Unable to process source entry: %s" % repr(self.source))
        else:
            out_str = self.source

        if pad:
            out_str = out_str.ljust(44, ' ')

        return out_str

    def to_fstab_entry(self):
        """
        Prints the object as a fstab entry
        """
        if not hasattr(self, 'type'):
            raise ValueError("Mount type not specified, required for fstab entries.")

        out_str = ''
        out_str += self.get_source(pad=True)
        out_str += self.destination.ljust(16, ' ')
        out_str += self.type.ljust(8, ' ')
        if hasattr(self, 'options'):
            out_str += self.options
        return out_str

    def to_mount_cmd(self):
        """
        Prints the object as a mount command
        """
        out_str = f"mount {self.get_source()} {self.destination}"

        if hasattr(self, 'options'):
            out_str += f" -o {self.options}"

        if hasattr(self, 'type'):
            out_str += f" -t {self.type}"

        return out_str

    def __str__(self):
        """
        Returns the fstab entry if it's not a base mount,
        otherwise returns the mount command
        """
        if self.base_mount:
            self.logger.debug("Base mount: %s" % self.destination)
            return self.to_mount_cmd()
        else:
            self.logger.debug("Fstab mount: %s" % self.destination)
            return self.to_fstab_entry()

