__author__ = 'desultory'
__version__ = '0.2.5'

from pathlib import Path


def generate_fstab(self):
    """
    Generates the fstab from the mounts
    """
    fstab_path = self.config_dict['out_dir'] / 'etc/fstab'

    with open(fstab_path, 'w') as fstab_file:
        for mount, config in self.config_dict['mounts'].items():
            fstab_file.write(f"{config}\n")


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
    # lol
    return ["mount -a"]


def mount_root(self):
    """
    Mounts the root partition
    """
    mount_str = "mount "
    if 'label' in self.config_dict['root_mount']:
        mount_str += f"-L {self.config_dict['root_mount']['label']} "
    elif 'uuid' in self.config_dict['root_mount']:
        mount_str += f"-U {self.config_dict['root_mount']['uuid']} "
    else:
        self.logger.critical("UNABLE TO CONFIGURE ROOT MOUNT")
        self.logger.critical("""
                             A root mount must be configured with:
                             root_mount:
                               mount_type: parameter
                             ex:
                             root_mount:
                               label: rootfs
                             """)
    mount_str += "/mnt/root || (echo 'Failed to mount root partition' && bash)"
    return [mount_str]


def clean_mounts(self):
    """
    Generates init lines to unmount all mounts
    """
    return [f"umount /{mount}" for mount in self.config_dict['mounts']]


def _process_mounts_multi(self, key, mount_config):
    """
    Processes the passed mounts into fstab mount objects
    under 'fstab_mounts'
    """
    if 'destination' not in mount_config:
        mount_config['destination'] = f"/{key}"  # prepend a slash

    try:
        self['mounts'][key] = FstabMount(**mount_config)
        self['paths'].append(mount_config['destination'])
    except ValueError as e:
        self.logger.error("Unable to process mount: %s" % key)
        self.logger.error(e)


class FstabMount:
    parameters = {'destination': True,
                  'source': True,
                  'type': True,
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

    def validate_destination(self, destination):
        """
        Validates the destination
        """
        if not destination.startswith('/'):
            return False
        return True

    def get_source(self):
        """
        returns the fstab source string based on the config
        """
        if isinstance(self.source, dict):
            if 'uuid' in self.source:
                return f"UUID={self.source['uuid']}".ljust(44, ' ')
            else:
                raise ValueError("Unable to process source entry: %s" % repr(self.source))
        else:
            return self.source.ljust(16, ' ')

    def __str__(self):
        """
        Prints the object as a fstab entry
        """
        out_str = ''
        out_str += self.get_source()
        out_str += self.destination.ljust(16, ' ')
        out_str += self.type.ljust(8, ' ')
        if hasattr(self, 'options'):
            out_str += self.options
        return out_str
