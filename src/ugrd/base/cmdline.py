__author__ = 'desultory'
__version__ = '1.0.0'


def parse_cmdline(self) -> str:
    """ Returns bash script to parse /proc/cmdline """
    return ['echo "Parsing /proc/cmdline: $(cat /proc/cmdline)"',
            r'grep -oP "(?<=root=)[^\s]+" /proc/cmdline > /run/CMDLINE_ROOT',
            r'''echo "$(grep -oP "(?<=roottype=)[^\s]+" /proc/cmdline || echo 'auto')" > /run/CMDLINE_ROOT_TYPE''',
            r'''echo "$(grep -oP '(?<=rootflags=)[^\s]+' /proc/cmdline || echo 'defaults,ro')" > /run/CMDLINE_ROOT_FLAGS''']


def mount_cmdline_root(self) -> str:
    """ Returns bash script to mount root partition based on /proc/cmdline """
    return ['if [ -n "$(cat /run/CMDLINE_ROOT)" ]; then',
            '    echo "Mounting root partition based on /proc/cmdline: $(cat /run/CMDLINE_ROOT) -t $(cat /run/CMDLINE_ROOT_TYPE) -o $(cat /run/CMDLINE_ROOT_FLAGS)"',
            '    mount $(cat /run/CMDLINE_ROOT) $(cat /run/MOUNTS_ROOT_TARGET) -t $(cat /run/CMDLINE_ROOT_TYPE) -o $(cat /run/CMDLINE_ROOT_FLAGS)',
            'fi',
            'if [ $? -ne 0 ] || [ -z "$(cat /run/CMDLINE_ROOT)" ]; then',
            '    echo "Failed to mount the root parition using /proc/cmdline"',
            '    mount_root',
            'fi']
