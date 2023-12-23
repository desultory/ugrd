__author__ = 'desultory'
__version__ = '2.2.0'

from importlib.metadata import version


def do_switch_root(self) -> str:
    """
    Should be the final statement, switches root.
    Checks if the root mount is mounted, if not, starts a bash shell
    """
    mount_dest = self['mounts']['root']['destination'] if not self.get('switch_root_target') else self['switch_root_target']
    out = [f"echo 'Checking root mount: {mount_dest}'",
           f"if grep -q ' {mount_dest} ' /proc/mounts ; then",
           f'    echo "Completed UGRD v{version("ugrd")}."',
           f"    exec switch_root {mount_dest} /sbin/init",
           "else",
           "    echo 'Root mount not found, restarting'",
           "    exec /init",
           "fi"]
    return out

