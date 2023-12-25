__author__ = 'desultory'
__version__ = '0.3.3'


def parse_cmdline(self) -> str:
    """ Returns bash script to parse /proc/cmdline """
    return ["echo 'Parsing /proc/cmdline'",
            r"export CMDLINE_ROOT=$(grep -oP '(?<=root=)[^\s]+' /proc/cmdline)"]


def refactor_mounts(self):
    """
    Refactors the imports['init_mount'] list to just be mount_cmdline_root.
    Adds moved imports to self['_init_mount'] for later use.
    """
    self['_init_mount'] = []

    for func in self['imports']['init_mount'].copy():
        if func.__name__ == 'mount_cmdline_root':
            continue
        if func not in self['_init_mount']:
            self['_init_mount'].append(func)
        self['imports']['init_mount'].remove(func)


def mount_cmdline_root(self) -> str:
    """ Returns bash script to mount root partition based on /proc/cmdline """
    mount_dest = self['mounts']['root']['destination'] if not self.get('switch_root_target') else self['switch_root_target']
    out_str = ["echo 'Mounting root partition based on /proc/cmdline'",
               f"mount $CMDLINE_ROOT {mount_dest} -o ro",
               'if [ $? -ne 0 ]; then',
               '    echo "Failed to mount the root parition using /proc/cmdline"']
    for name in self['_init_mount']:
        out_str.append(f'    {name}')
    out_str.append('fi')
    return out_str
