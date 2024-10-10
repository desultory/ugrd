__author__ = 'desultory'
__version__ = '4.9.1'

from importlib.metadata import version
from pathlib import Path

from zenlib.util import contains, unset


@contains('hostonly')
def _validate_init_target(self) -> None:
    if not self['init_target'].exists():
        raise FileNotFoundError('init_target not found at: %s' % self['init_target'])
    if 'systemd' in str(self['init_target']):
        self.logger.warning("'ugrd.fs.fakeudev' may be required if systemd mounts stall on boot.")


def _process_init_target(self, target: Path) -> None:
    if not isinstance(target, Path):
        target = Path(target).resolve()
    self.data['init_target'] = target
    self['exports']['init'] = self['init_target']
    _validate_init_target(self)


def _process_loglevel(self, loglevel: int) -> None:
    """ Sets the loglevel. """
    self.data['loglevel'] = int(loglevel)
    self['exports']['loglevel'] = loglevel


@unset('init_target', 'init_target is already set, skipping autodetection.', log_level=30)
def _process_autodetect_init(self, state) -> None:
    self.data['autodetect_init'] = state


@contains('autodetect_init', log_level=30)
def autodetect_init(self) -> None:
    """ Autodetects the init_target. """
    from shutil import which
    if init := which('init'):
        self.logger.info('Detected init at: %s', init)
        self['init_target'] = init
    else:
        raise FileNotFoundError('init_target is not specified and could not be detected.')


def _find_init(self) -> str:
    """ Returns bash to find the init_target. """
    return ['for init_path in "/sbin/init" "/bin/init" "/init"; do',
            '    if [ -e "$(readvar MOUNTS_ROOT_TARGET)$init_path" ] ; then',
            '        einfo "Found init at: $(readvar MOUNTS_ROOT_TARGET)$init_path"',
            '        setvar init "$init_path"',
            '        return',
            '    fi',
            'done',
            'eerror "Unable to find init."',
            'return 1']


def set_loglevel(self) -> list[str]:
    """ Returns bash to set the log level. """
    return 'readvar loglevel > /proc/sys/kernel/printk'


@contains('init_target', 'init_target must be set.', raise_exception=True)
def do_switch_root(self) -> list[str]:
    """
    Should be the final statement, switches root.
    Checks if the root mount is mounted and that it contains an init.
    If not, it restarts UGRD.
    """
    return ['if [ $$ -ne 1 ] ; then',
            '    eerror "Cannot switch_root from PID: $$, exiting."',
            '    exit 1',
            'fi',
            'init_target=$(readvar init) || rd_fail "init_target not set."',  # should be set, if unset, checks fail
            'einfo "Checking root mount: $(readvar MOUNTS_ROOT_TARGET)"',
            'if ! grep -q " $(readvar MOUNTS_ROOT_TARGET) " /proc/mounts ; then',
            '    rd_fail "Root not found at: $(readvar MOUNTS_ROOT_TARGET)"',
            'elif [ ! -e "$(readvar MOUNTS_ROOT_TARGET)${init_target}" ] ; then',
            '    ewarn "$init_target not found at: $(readvar MOUNTS_ROOT_TARGET)"',
            r'    einfo "Target root contents:\n$(ls -l "$(readvar MOUNTS_ROOT_TARGET)")"',
            '    if _find_init ; then',  # This redefineds the var, so readvar instaed of using $init_target
            '        einfo "Switching root to: $(readvar MOUNTS_ROOT_TARGET) $(readvar init)"',
            '        exec switch_root "$(readvar MOUNTS_ROOT_TARGET)" "$(readvar init)"',
            '    fi',
            '    rd_fail "Unable to find init."',
            'else',
            f'    einfo "Completed UGRD v{version("ugrd")}."',
            '    einfo "Switching root to: $(readvar MOUNTS_ROOT_TARGET) $init_target"',
            '    exec switch_root "$(readvar MOUNTS_ROOT_TARGET)" "$init_target"',
            "fi"]


def rd_restart(self) -> str:
    """ Restart the initramfs, exit if not PID 1, otherwise exec /init. """
    return ['if [ "$$" -eq 1 ]; then',
            '    einfo "Restarting init"',
            '    exec /init ; exit',
            'else',
            '    ewarn "PID is not 1, exiting: $$"',
            '    exit 1',
            'fi']


def rd_fail(self) -> list[str]:
    """ Function for when the initramfs fails to function. """
    return ['if [ -n "$1" ]; then',
            '    eerror "Failure: $1"',
            'else',
            '    eerror "UGRD failed."',
            'fi',
            'prompt_user "Press enter to display debug info."',
            r'eerror "Loaded modules:\n$(cat /proc/modules)"',
            r'eerror "Block devices:\n$(blkid)"',
            r'eerror "Mounts:\n$(mount)"',
            'if [ "$(readvar recovery)" == "1" ]; then',
            '    einfo "Entering recovery shell"',
            '    bash -l',
            'fi',
            'prompt_user "Press enter to restart init."',
            'rd_restart']


def setvar(self) -> str:
    """ Returns a bash function that sets a variable in /run/vars/{name}. """
    return ['if check_var debug; then',
            '    edebug "Setting $1 to $2"',
            'fi',
            'echo -n "$2" > "/run/vars/${1}"']


def readvar(self) -> str:
    """
    Returns a bash function that reads a variable from /run/vars/{name}.
    The second arg can be a default value.
    If no default is supplied, and the variable is not found, it returns an empty string.
    """
    return 'cat "/run/vars/${1}" 2>/dev/null || echo "${2}"'


def check_var(self) -> str:
    """
    Returns a bash function that checks the value of a variable.
    if it's not set, tries to read the cmdline.
    """
    return ['if [ -z "$(readvar "$1")" ]; then',  # preferably the variable is set, because this is slower
            r'''    cmdline=$(awk -F '--' '{print $1}' /proc/cmdline)''',  # Get everything before '--'
            r'    if grep -qE "(^|\s)$1(\s|$)" <<< "$cmdline"; then',
            '        return 0',
            '    fi',
            '    return 1',
            'fi',
            'if [ "$(readvar "$1")" == "1" ]; then',
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


def retry(self) -> str:
    """
    Returns a bash function that retries a command some number of times.
    The first argument is the number of retries. if 0, it retries 100 times.
    The second argument is the timeout in seconds.
    The remaining arguments represent the command to run.
    """
    return ['retries=${1}',
            'timeout=${2}',
            'shift 2',
            'if [ "$retries" -eq 0 ]; then',
            '    "$@"',  # If retries is 0, just run the command
            '    return "$?"',
            'elif [ "$retries" -lt 0 ]; then',
            '    retries=100',
            'fi',
            'i=-1; while [ "$((i += 1))" -lt "$retries" ]; do',
            '    if "$@"; then',
            '        return 0',
            '    fi',
            r'    ewarn "[${i}/${retries}] Failed: ${*}"',
            '    if [ "$i" -lt "$((retries - 1))" ]; then',
            '        prompt_user "Retrying in: ${timeout}s" "$timeout"',
            '    fi',
            'done',
            'return 1']


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


def eerror(self) -> str:
    """ Returns a bash function like eerror. """
    return r'echo -e "\e[1;31m *\e[0m ${*}"'


