__author__ = 'desultory'
__version__ = '0.1.7'


def generate_fstab(self):
    """
    Generates the fstab from the mounts
    """
    with open(f"{self.out_dir}/etc/fstab", 'w') as fstab_file:
        for mount, config in self.config_dict['mounts'].items():
            fstab_file.write(f"{config}\n")


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
    self['mounts'][key] = FstabMount(destination=f"/{key}", **mount_config)


class FstabMount:
    parameters = {'destination': True,
                  'source': True,
                  'type': True,
                  'options': False}

    def __init__(self, *args, **kwargs):
        for parameter in self.parameters:
            if kwargs.get(parameter):
                setattr(self, parameter, kwargs.pop(parameter))
            elif self.parameters[parameter]:
                raise ValueError("Required parameter was not passed: %s" % parameter)

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
