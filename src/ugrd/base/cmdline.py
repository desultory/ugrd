__author__ = 'desultory'
__version__ = '0.6.5'


def parse_cmdline(self) -> str:
    """ Returns bash script to parse /proc/cmdline """
    return ['echo "Parsing /proc/cmdline: $(cat /proc/cmdline)"',
            r"export CMDLINE_ROOT=$(grep -oP '(?<=root=)[^\s]+' /proc/cmdline)",
            r"export CMDLINE_ROOTFLAGS=$(grep -oP '(?<=rootflags=)[^\s]+' /proc/cmdline)"]


def refactor_mounts(self):
    """
    Refactors the imports['init_mount'] list to just be mount_cmdline_root.
    Add moved imports to self['imports']['functions'] to be called at runtime.
    Adds moved imports to self['_init_mount'] for later use.
    """
    self['_init_mount'] = []

    for func in self['imports']['init_mount'].copy():
        if func.__name__ == 'mount_cmdline_root':
            continue
        if func not in self['_init_mount']:
            self['_init_mount'].append(func)
            self['imports']['functions'].append(func)
        self['imports']['init_mount'].remove(func)


def mount_cmdline_root(self) -> str:
    """ Returns bash script to mount root partition based on /proc/cmdline """
    mount_dest = self['mounts']['root']['destination'] if not self.get('switch_root_target') else self['switch_root_target']
    out_str = ['if [ -n "$CMDLINE_ROOT" ]; then',
               '    echo "Mounting root partition based on /proc/cmdline: $CMDLINE_ROOT -o $CMDLINE_ROOTFLAGS"',
               f'    mount $CMDLINE_ROOT {mount_dest} -o $CMDLINE_ROOTFLAGS',
               'fi',
               'if [ $? -ne 0 ] || [ -z "$CMDLINE_ROOT" ]; then',
               '    echo "Failed to mount the root parition using /proc/cmdline"']
    for func in self['_init_mount']:
        if not func():
            continue
        out_str.append(f'    {func.__name__}')
    out_str.append('fi')
    return out_str
