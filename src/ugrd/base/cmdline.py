__author__ = 'desultory'
__version__ = '0.8.0'


def parse_cmdline(self) -> str:
    """ Returns bash script to parse /proc/cmdline """
    return ['echo "Parsing /proc/cmdline: $(cat /proc/cmdline)"',
            r'grep -oP "(?<=root=)[^\s]+" /proc/cmdline) > /run/CMDLINE_ROOT',
            r'grep -oP "(?<=rootflags=)[^\s]+" /proc/cmdline) > /run/CMDLINE_ROOTFLAGS']


def mount_cmdline_root(self) -> str:
    """ Returns bash script to mount root partition based on /proc/cmdline """
    return ['if [ -n "$(cat /run/CMDLINE_ROOT)" ]; then',
            '    echo "Mounting root partition based on /proc/cmdline: $(cat /run/CMDLINE_ROOT) -o $(cat /run/CMDLINE_ROOTFLAGS)"',
            '    mount $(cat /run/CMDLINE_ROOT) $(cat /run/MOUNTS_ROOT_TARGET) -o $(cat /run/CMDLINE_ROOTFLAGS)',
            'fi',
            'if [ $? -ne 0 ] || [ -z "$(cat /run/CMDLINE_ROOT)" ]; then',
            '    echo "Failed to mount the root parition using /proc/cmdline"',
            '    mount_root',
            'fi']
