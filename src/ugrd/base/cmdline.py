__author__ = 'desultory'
__version__ = '0.2.0'


def parse_cmdline(self) -> str:
    """ Returns bash script to parse /proc/cmdline """
    return ["echo 'Parsing /proc/cmdline'",
            r"export CMDLINE_ROOT=$(grep -oP '(?<=root=)[^\s]+' /proc/cmdline)"]


def mount_cmdline_root(self) -> str:
    """ Returns bash script to mount root partition based on /proc/cmdline """
    mount_dest = self['mounts']['root']['destination'] if not self.get('switch_root_target') else self['switch_root_target']
    return ["echo 'Mounting root partition based on /proc/cmdline'",
            f"mount $CMDLINE_ROOT {mount_dest} -o ro",
            'if [ $? -ne 0 ]; then',
            '    echo "Failed to mount the root parition using /proc/cmdline"',
            '    mount_root',
            'fi']
