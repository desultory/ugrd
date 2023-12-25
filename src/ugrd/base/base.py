__author__ = 'desultory'
__version__ = '2.7.0'

from importlib.metadata import version


def _process_switch_root_target(self, target) -> None:
    """ Processes the switch_root_target variable. Adds it to the paths. """
    dict.__setitem__(self, 'switch_root_target', target)
    self['paths'] = target


def export_switchroot_target(self) -> str:
    """ Returns bash to export the switch_root_target variable to MOUNTS_ROOT_PATH, update the mounts dict so the fstab is accurate """
    if target := self.get('switch_root_target'):
        return f'export SWITCH_ROOT_TARGET="{target}"'
    else:
        return 'export SWITCH_ROOT_TARGET="$MOUNTS_ROOT_TARGET"'


def do_switch_root(self) -> str:
    """
    Should be the final statement, switches root.
    Checks if the root mount is mounted, if not, starts a bash shell
    """
    out = ['echo "Checking root mount: $MOUNTS_ROOT_TARGET"',
           'if grep -q " $MOUNTS_ROOT_TARGET  " /proc/mounts ; then',
           f'    echo "Completed UGRD v{version("ugrd")}."',
           '    exec switch_root "$MOUNTS_ROOT_TARGET"  /sbin/init',
           "else",
           '    echo "Root mount not found at: $MOUNTS_ROOT_TARGET"',
           '    read -p "Press enter to restart UGRD."',
           "    exec /init",
           "fi"]
    return out

