__author__ = 'desultory'
__version__ = '3.8.0'

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
            '    ewarn "Root mount not found at: $(readvar MOUNTS_ROOT_TARGET)"',
            r'    einfo -e "Current block devices:\n$(blkid)"',
            '    read -p "Press enter to restart UGRD."',
            '    exec /init',
            'elif [ ! -e $(readvar SWITCH_ROOT_TARGET)$(readvar INIT_TARGET) ] ; then',
            '    ewarn "$(readvar INIT_TARGET) not found at: $(readvar SWITCH_ROOT_TARGET)"',
            r'    einfo -e "Target root contents:\n$(ls -l $(readvar SWITCH_ROOT_TARGET))"',
            '    if _find_init ; then',
            '        einfo "Switching root to: $(readvar SWITCH_ROOT_TARGET) $(readvar INIT_TARGET)"',
            '        exec switch_root "$(readvar SWITCH_ROOT_TARGET)" "$(readvar INIT_TARGET)"',
            '    fi',
            '    read -p "Press enter to restart UGRD."',
            '    exec /init',
            'else',
            f'    einfo "Completed UGRD v{version("ugrd")}."',
            '    einfo "Switching root to: $(readvar SWITCH_ROOT_TARGET) $(readvar INIT_TARGET)"',
            '    exec switch_root "$(readvar SWITCH_ROOT_TARGET)" "$(readvar INIT_TARGET)"',
            "fi"]


def setvar(self) -> str:
    """ Returns a bash function that sets a variable in /run/vars/{name}. """
    return ['setvar() {',
            '    echo "$2" > "/run/vars/${1}"',
            '}']


def readvar(self) -> str:
    """ Returns a bash function that reads a variable from /run/vars/{name}. """
    return ['readvar() {',
            '    cat "/run/vars/${1}"',
            '}']


# To feel more at home
def einfo(self) -> str:
    """ Returns a bash function like einfo. """
    return ['einfo() {',
            '    if [ "$QUIET" == "1" ]; then',
            '        return',
            '    fi',
            r'    echo -e "\e[1;32m*\e[0m ${*}" >&2',
            '}']


def ewarn(self) -> str:
    """ Returns a bash function like ewarn. """
    return ['ewarn() {',
            '    if [ "$QUIET" == "1" ]; then',
            '        return',
            '    fi',
            r'    echo -e "\e[1;33m*\e[0m ${*}" >&2',
            '}']

