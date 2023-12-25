__author__ = 'desultory'
__version__ = '0.7.2'


def parse_cmdline(self) -> str:
    """ Returns bash script to parse /proc/cmdline """
    return ['echo "Parsing /proc/cmdline: $(cat /proc/cmdline)"',
            r"""export CMDLINE_ROOT="$(grep -oP '(?<=root=)[^\s]+' /proc/cmdline)" """,
            r"""export CMDLINE_ROOTFLAGS="$(grep -oP '(?<=rootflags=)[^\s]+' /proc/cmdline || echo 'defaults,ro')" """]


def mount_cmdline_root(self) -> str:
    """ Returns bash script to mount root partition based on /proc/cmdline """
    return ['if [ -n "$CMDLINE_ROOT" ]; then',
            '    echo "Mounting root partition based on /proc/cmdline: $CMDLINE_ROOT -o $CMDLINE_ROOTFLAGS"',
            '    mount $CMDLINE_ROOT $MOUNTS_ROOT_TARGET -o $CMDLINE_ROOTFLAGS',
            'fi',
            'if [ $? -ne 0 ] || [ -z "$CMDLINE_ROOT" ]; then',
            '    echo "Failed to mount the root parition using /proc/cmdline"',
            '    mount_root',
            'fi']
