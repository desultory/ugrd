__author__ = 'desultory'
__version__ = '2.4.0'


def parse_cmdline_bool(self) -> str:
    """
    Returns a bash script to parse a boolean value from /proc/cmdline
    The only argument is the name of the variable to be read/set
    """
    return ['edebug "Parsing cmdline bool: $1"',
            r'setvar "$1" "$(grep -qE "(^|\s)$1(\s|$)" /proc/cmdline && echo 1 || echo 0)"']


def parse_cmdline_str(self) -> str:
    """
    Returns a bash script to parse a string value from /proc/cmdline
    The only argument is the name of the variable to be read/set
    """
    return ['edebug "Parsing cmdline string: $1"',
            r'val=$(grep -oP "(?<=$1=)[^\s]+" /proc/cmdline)',
            'if [ -n "$val" ]; then',
            '    edebug "Parsed $1: $val"',
            '    setvar "$1" "$val"',
            'fi']


def parse_cmdline(self) -> str:
    """ Returns bash script to parse /proc/cmdline """
    return [r'''cmdline=$(awk -F '--' '{print $1}' /proc/cmdline)''',  # Get everything before '--'
            r'''setvar INIT_ARGS "$(awk -F '--' '{print $2}' /proc/cmdline)"''',  # Get everything after '--'
            f'''for bool in {" ".join([f'"{bool}"' for bool in self['cmdline_bools']])}; do''',
            '    parse_cmdline_bool "$bool"',
            'done',
            f'''for string in {" ".join([f'"{string}"' for string in self['cmdline_strings']])}; do''',
            '    parse_cmdline_str "$string"',
            'done',
            'einfo "Parsed cmdline: $cmdline"']


def mount_cmdline_root(self) -> str:
    """ Returns bash script to mount root partition based on /proc/cmdline """
    return ['root=$(readvar root)',
            'if [ -z "$root" ]; then',
            '    edebug "No root partition specified in /proc/cmdline, falling back to mount_root"',
            '    mount_root',
            '    return',
            'fi',
            'roottype="$(readvar roottype auto)"',
            '''rootflags="$(readvar rootflags 'defaults,ro')"''',
            'einfo "Mounting root partition based on /proc/cmdline: $root -t $roottype -o $rootflags"',
            'if ! mount "$root" "$(readvar MOUNTS_ROOT_TARGET)" -t "$roottype" -o "$rootflags"; then',
            '    eerror "Failed to mount the root partition using /proc/cmdline: $root -t $roottype -o $rootflags"',
            '    mount_root',
            'fi']


def export_exports(self) -> list:
    """ Returns a bash script exporting all exports defined in the exports key. """
    from importlib.metadata import version, PackageNotFoundError
    try:
        self['exports']['VERSION'] = version(__package__.split('.')[0])
    except PackageNotFoundError:
        self['exports']['VERSION'] = 9999
    return [f'setvar {key} "{value}"' for key, value in self['exports'].items()]
