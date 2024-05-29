__author__ = 'desultory'
__version__ = '1.2.1'


def parse_cmdline(self) -> str:
    """ Returns bash script to parse /proc/cmdline """
    return [r'grep -qE "(^\s)+quiet(\s|$)" /proc/cmdline && echo "1" > /run/QUIET',
            r'grep -oP "(?<=root=)[^\s]+" /proc/cmdline > /run/CMDLINE_ROOT',
            r'''echo "$(grep -oP "(?<=roottype=)[^\s]+" /proc/cmdline || echo 'auto')" > /run/CMDLINE_ROOT_TYPE''',
            r'''echo "$(grep -oP '(?<=rootflags=)[^\s]+' /proc/cmdline || echo 'defaults,ro')" > /run/CMDLINE_ROOT_FLAGS''',
            'einfo "Parsed values: $(ls /run/)"']


def mount_cmdline_root(self) -> str:
    """ Returns bash script to mount root partition based on /proc/cmdline """
    return ['if [ -n "$(readvar CMDLINE_ROOT)" ]; then',
            '    einfo "Mounting root partition based on /proc/cmdline: $(readvar CMDLINE_ROOT) -t $(readvar CMDLINE_ROOT_TYPE) -o $(readvar CMDLINE_ROOT_FLAGS)"',
            '    mount $(readvar CMDLINE_ROOT) $(readvar MOUNTS_ROOT_TARGET) -t $(readvar CMDLINE_ROOT_TYPE) -o $(readvar CMDLINE_ROOT_FLAGS)',
            'fi',
            'if [ $? -ne 0 ] || [ -z "$(readvar CMDLINE_ROOT)" ]; then',
            '    ewarn "Failed to mount the root parition using /proc/cmdline"',
            '    mount_root',
            'fi']
