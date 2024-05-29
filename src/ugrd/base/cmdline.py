__author__ = 'desultory'
__version__ = '1.2.3'


def parse_cmdline(self) -> str:
    """ Returns bash script to parse /proc/cmdline """
    return [r'grep -qE "(^|\s)quiet(\s|$)" /proc/cmdline && setvar QUIET 1 || setvar QUIET 0',
            r'setvar CMDLINE_ROOT $(grep -oP "(?<=root=)[^\s]+" /proc/cmdline)',
            r'setvar CMDLINE_ROOT_TYPE $(grep -oP "(?<=roottype=)[^\s]+" /proc/cmdline || echo "auto")',
            r'setvar CMDLINE_ROOT_FLAGS $(grep -oP "(?<=rootflags=)[^\s]+" /proc/cmdline || echo "defaults,ro")',
            r'setvar RECOVERY_SHELL $(grep -qE "(^\s)+recovery(\s|$)" /proc/cmdline && echo 1 || echo 0)',
            'einfo "Parsed values: $(ls /run/vars)"']


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
