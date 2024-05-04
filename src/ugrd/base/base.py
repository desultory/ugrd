__author__ = 'desultory'
__version__ = '3.1.1'

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
    dict.__setitem__(self, 'init_target', state)
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


@check_dict('init_target', not_empty=True, raise_exception=True, message='init_target must be set.')
def do_switch_root(self) -> str:
    """
    Should be the final statement, switches root.
    Checks if the root mount is mounted and that it contains an init.
    If not, it restarts UGRD.
    """
    _validate_init_target(self)
    out = ['echo "Checking root mount: $(cat /run/MOUNTS_ROOT_TARGET)"',
           'if ! grep -q " $(cat /run/MOUNTS_ROOT_TARGET) " /proc/mounts ; then',
           '    echo "Root mount not found at: $(cat /run/MOUNTS_ROOT_TARGET)"',
           '    read -p "Press enter to restart UGRD."',
           "    exec /init",
           f"elif [ ! -e $(cat /run/MOUNTS_ROOT_TARGET){self['init_target']} ] ; then",
           f'    echo "{self["init_target"]} not found at: $(cat /run/MOUNTS_ROOT_TARGET)"',
           '    read -p "Press enter to restart UGRD."',
           '    exec /init',
           'else',
           f'    echo "Completed UGRD v{version("ugrd")}."',
           '    exec switch_root "$(cat /run/MOUNTS_ROOT_TARGET)" /sbin/init',
           "fi"]
    return out

