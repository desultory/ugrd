__author__ = 'desultory'
__version__ = '4.2.0'

from importlib.metadata import version
from pathlib import Path

from zenlib.util import check_dict


@check_dict('validate', value=True)
def _validate_init_target(self) -> None:
    if not self['init_target'].exists():
        raise FileNotFoundError('init_target not found at: %s', self['init_target'])


def _process_init_target(self, target: Path) -> None:
    if not isinstance(target, Path):
        target = Path(target).resolve()
    dict.__setitem__(self, 'init_target', target)


def _process_switch_root_target(self, target) -> None:
    """ Processes the switch_root_target variable. Adds it to the paths. """
    dict.__setitem__(self, 'switch_root_target', target)
    self['paths'] = target
    if self['mounts']['root']['destination'] != target:
        if str(self['mounts']['root']['destination']) != '/root':
            self.logger.warning("Root mount target set to '%s', updating to match switch root target: %s" %
                                (self['mounts']['root']['destination'], target))
        self['mounts']['root']['destination'] = target


@check_dict('init_target', unset=True, message='init_target already set.')
def _process_autodetect_init(self, state) -> None:
    from shutil import which
    dict.__setitem__(self, 'autodetect_init', state)
    if not state:
        return

    if init := which('init'):
        self.logger.info('Detected init at: %s', init)
        self['init_target'] = init
    else:
        raise FileNotFoundError('init_target is not specified and coud not be detected.')


def export_switchroot_target(self) -> str:
    """ Returns bash to export the switch_root_target variable to SWITCH_ROOT_TARGET. """
    if self['switch_root_target'] != str(self['mounts']['root']['destination']):
        self.logger.warning("Switch root/root mount mismatch; Root mount target set to '%s', switch root target is: %s" %
                            (self['mounts']['root']['destination'], self['switch_root_target']))
        self['mounts']['root']['destination'] = self['switch_root_target']
    return f'setvar SWITCH_ROOT_TARGET "{self["switch_root_target"]}"'


def export_init_target(self) -> str:
    """ Returns bash to export the init_target variable to MOUNTS_ROOT_TARGET. """
    _validate_init_target(self)
    return f'setvar INIT_TARGET "{self["init_target"]}"'


def _find_init(self) -> str:
    """ Returns bash to find the init_target. """
    return ['for init_path in "/sbin/init" "/bin/init" "/init"; do',
            '    if [ -e "$(readvar SWITCH_ROOT_TARGET)$init_path" ] ; then',
            '        einfo "Found init at: $(readvar SWITCH_ROOT_TARGET)$init_path"',
            '        setvar INIT_TARGET "$init_path"',
            '        return',
            '    fi',
            'done',
            'echo "Unable to find init."',
            'return 1']


@check_dict('init_target', not_empty=True, raise_exception=True, message='init_target must be set.')
def do_switch_root(self) -> str:
    """
    Should be the final statement, switches root.
    Checks if the root mount is mounted and that it contains an init.
    If not, it restarts UGRD.
    """
    return ['if [ $$ -ne 1 ] ; then',
            '    ewarn "Cannot switch_root from PID: $$, exiting."',
            '    exit 1',
            'fi',
            'echo "Checking root mount: $(readvar MOUNTS_ROOT_TARGET)"',
            'if ! grep -q " $(readvar MOUNTS_ROOT_TARGET) " /proc/mounts ; then',
            '    rd_fail "Root not found at: $(readvar MOUNTS_ROOT_TARGET)"',
            'elif [ ! -e $(readvar SWITCH_ROOT_TARGET)$(readvar INIT_TARGET) ] ; then',
            '    ewarn "$(readvar INIT_TARGET) not found at: $(readvar SWITCH_ROOT_TARGET)"',
            r'    einfo "Target root contents:\n$(ls -l $(readvar SWITCH_ROOT_TARGET))"',
            '    if _find_init ; then',
            '        einfo "Switching root to: $(readvar SWITCH_ROOT_TARGET) $(readvar INIT_TARGET)"',
            '        exec switch_root "$(readvar SWITCH_ROOT_TARGET)" "$(readvar INIT_TARGET)"',
            '    fi',
            '    rd_fail "Unable to find init."',
            'else',
            f'    einfo "Completed UGRD v{version("ugrd")}."',
            '    einfo "Switching root to: $(readvar SWITCH_ROOT_TARGET) $(readvar INIT_TARGET)"',
            '    exec switch_root "$(readvar SWITCH_ROOT_TARGET)" "$(readvar INIT_TARGET)"',
            "fi"]


def rd_fail(self) -> list[str]:
    """ Function for when the initramfs fails to function. """
    return ['if [ -n "$1" ]; then',
            '    ewarn "Mount failed: $1"',
            'else',
            '    ewarn "Mount failed"',
            'fi',
            'prompt_user "Press enter to display debug info."',
            r'einfo "Loaded modules:\n$(cat /proc/modules)"',
            r'einfo "Block devices:\n$(blkid)"',
            r'einfo "Mounts:\n$(mount)"',
            'if [ "$(readvar RECOVERY_SHELL)" == "1" ]; then',
            '    einfo "Entering recovery shell"',
            '    bash -l',
            'fi',
            'prompt_user "Press enter to restart init."',
            'if [ "$$" -eq 1 ]; then',
            '    einfo "Restarting init"',
            '    exec /init ; exit',
            'else',
            '    ewarn "PID is not 1, exiting: $$"',
            '    exit',
            'fi']


def setvar(self) -> str:
    """ Returns a bash function that sets a variable in /run/vars/{name}. """
    return ['if check_var debug; then',
            '    edebug "Setting $1 to $2"',
            'fi',
            'echo -n "$2" > "/run/vars/${1}"']


def readvar(self) -> str:
    """
    Returns a bash function that reads a variable from /run/vars/{name}.
    If the variable is not found, it returns an empty string.
    """
    return 'cat "/run/vars/${1}" 2>/dev/null || echo ""'


def check_var(self) -> str:
    """
    Returns a bash function that checks the value of a variable.
    if it's not set, tries to read the cmdline.
    """
    return ['if [ -z "$(readvar $1)" ]; then',
            '    if [ -e /proc/cmdline ]; then',
            r'        return $(grep -qE "(^|\s)$1(\s|$)" /proc/cmdline)',
            '    fi',
            '    return 1',
            'fi',
            'if [ "$(readvar $1)" == "1" ]; then',
            '    return 0',
            'fi',
            'return 1']


def prompt_user(self) -> str:
    """
    Returns a bash function that pauses until the user presses enter.
    The first argument is the prompt message.
    The second argument is the timeout in seconds.
    """
    return ['prompt=${1:-"Press enter to continue."}',
            r'echo -e "\e[1;35m *\e[0m $prompt"',
            'if [ -n "$2" ]; then',
            '    read -t "$2" -rs',
            'else',
            '    read -rs',
            'fi']


# To feel more at home
def edebug(self) -> str:
    """ Returns a bash function like edebug. """
    return ['if check_var quiet; then',
            '    return',
            'fi',
            'if [ "$(readvar debug)" != "1" ]; then',
            '    return',
            'fi',
            r'echo -e "\e[1;34m *\e[0m ${*}"'
            ]


def einfo(self) -> str:
    """ Returns a bash function like einfo. """
    return ['if check_var quiet; then',
            '    return',
            'fi',
            r'echo -e "\e[1;32m *\e[0m ${*}"'
            ]


def ewarn(self) -> str:
    """ Returns a bash function like ewarn. """
    return ['if check_var quiet; then',
            '    return',
            'fi',
            r'echo -e "\e[1;33m *\e[0m ${*}"']

