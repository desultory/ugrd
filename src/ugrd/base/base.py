__author__ = 'desultory'
__version__ = '2.8.1'

from importlib.metadata import version


def _process_switch_root_target(self, target) -> None:
    """ Processes the switch_root_target variable. Adds it to the paths. """
    dict.__setitem__(self, 'switch_root_target', target)
    self['paths'] = target


def export_switchroot_target(self) -> str:
    """ Returns bash to export the switch_root_target variable to MOUNTS_ROOT_PATH. """
    if target := self.get('switch_root_target'):
        return f'echo "{target}" > /run/SWITCH_ROOT_TARGET'
    else:
        return 'cp /run/MOUNTS_ROOT_PATH /run/SWITCH_ROOT_TARGET'


def do_switch_root(self) -> str:
    """
    Should be the final statement, switches root.
    Checks if the root mount is mounted, if not, starts a bash shell
    """
    out = ['echo "Checking root mount: $(cat /run/MOUNTS_ROOT_TARGET)"',
           'if grep -q " $(cat /run/MOUNTS_ROOT_TARGET) " /proc/mounts ; then',
           f'    echo "Completed UGRD v{version("ugrd")}."',
           '    exec switch_root "$(cat /run/MOUNTS_ROOT_TARGET)" /sbin/init',
           "else",
           '    echo "Root mount not found at: $(cat /run/MOUNTS_ROOT_TARGET)"',
           '    read -p "Press enter to restart UGRD."',
           "    exec /init",
           "fi"]
    return out

