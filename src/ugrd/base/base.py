__author__ = 'desultory'
__version__ = '3.3.0'

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
    """ Returns bash to export the switch_root_target variable to MOUNTS_ROOT_TARGET. """
    if target := self.get('switch_root_target'):
        return f'echo "{target}" > /run/SWITCH_ROOT_TARGET'
    else:
        return 'cp /run/MOUNTS_ROOT_TARGET /run/SWITCH_ROOT_TARGET'


def export_init_target(self) -> str:
    """ Returns bash to export the init_target variable to MOUNTS_ROOT_TARGET. """
    _validate_init_target(self)
    return f'echo "{self["init_target"]}" > /run/INIT_TARGET'


def _find_init(self) -> str:
    """ Returns bash to find the init_target. """
    return ['for init_path in "/sbin/init" "/bin/init" "/init"; do',
            '    if [ -e "$(cat /run/MOUNTS_ROOT_TARGET)$init_path" ] ; then',
            '        echo "Found init at: $(cat /run/MOUNTS_ROOT_TARGET)$init_path"',
            '        echo "$init_path" > /run/INIT_TARGET',
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
            '    echo "Cannot switch_root from PID: $$, exiting."',
            '    exit 1',
            'fi',
            'echo "Checking root mount: $(cat /run/MOUNTS_ROOT_TARGET)"',
            'if ! grep -q " $(cat /run/MOUNTS_ROOT_TARGET) " /proc/mounts ; then',
            '    echo "Root mount not found at: $(cat /run/MOUNTS_ROOT_TARGET)"',
            r'    echo -e "Current block devices:\n$(blkid)"',
            '    read -p "Press enter to restart UGRD."',
            '    exec /init',
            'elif [ ! -e $(cat /run/MOUNTS_ROOT_TARGET)$(cat /run/INIT_TARGET) ] ; then',
            '    echo "$(cat /run/INIT_TARGET) not found at: $(cat /run/MOUNTS_ROOT_TARGET)"',
            r'    echo -e "Root contents:\n$(ls -l $(cat /run/MOUNTS_ROOT_TARGET))"',
            '    if _find_init ; then',
            '        echo "Switching root to: $(cat /run/MOUNTS_ROOT_TARGET) $(cat /run/INIT_TARGET)"',
            '        exec switch_root "$(cat /run/MOUNTS_ROOT_TARGET)" "$(cat /run/INIT_TARGET)"',
            '    fi',
            '    read -p "Press enter to restart UGRD."',
            '    exec /init',
            'else',
            f'    echo "Completed UGRD v{version("ugrd")}."',
            '    echo "Switching root to: $(cat /run/MOUNTS_ROOT_TARGET) $(cat /run/INIT_TARGET)"',
            '    exec switch_root "$(cat /run/MOUNTS_ROOT_TARGET)" "$(cat /run/INIT_TARGET)"',
            "fi"]

