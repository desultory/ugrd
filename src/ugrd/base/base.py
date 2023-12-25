__author__ = 'desultory'
__version__ = '3.0.2'

from importlib.metadata import version


def _process_switch_root_target(self, target) -> None:
    """ Processes the switch_root_target variable. Adds it to the paths. """
    dict.__setitem__(self, 'switch_root_target', target)
    self['paths'] = target


def export_switchroot_target(self) -> str:
    """ Returns bash to export the switch_root_target variable to MOUNTS_ROOT_TARGET. """
    if target := self.get('switch_root_target'):
        return f'echo "{target}" > /run/SWITCH_ROOT_TARGET'
    else:
        return 'cp /run/MOUNTS_ROOT_TARGET /run/SWITCH_ROOT_TARGET'


def do_switch_root(self) -> str:
    """
    Should be the final statement, switches root.
    Checks if the root mount is mounted and that it contains an init.
    If not, it restarts UGRD.
    """
    out = ['echo "Checking root mount: $(cat /run/MOUNTS_ROOT_TARGET)"',
           'if ! grep -q " $(cat /run/MOUNTS_ROOT_TARGET) " /proc/mounts ; then',
           '    echo "Root mount not found at: $(cat /run/MOUNTS_ROOT_TARGET)"',
           '    read -p "Press enter to restart UGRD."',
           "    exec /init",
           "elif [ ! -e $(cat /run/MOUNTS_ROOT_TARGET)/sbin/init ] ; then",
           '    echo "/sbin/init not found at: $(cat /run/MOUNTS_ROOT_TARGET)"',
           '    read -p "Press enter to restart UGRD."',
           '    exec /init',
           'else',
           f'    echo "Completed UGRD v{version("ugrd")}."',
           '    exec switch_root "$(cat /run/MOUNTS_ROOT_TARGET)" /sbin/init',
           "fi"]
    return out

