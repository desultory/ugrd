__author__ = 'desultory'
__version__ = '1.3.0'


def do_switch_root(self) -> str:
    """
    Should be the final statement, switches root.
    Checks if the root mount is mounted, if not, starts a bash shell
    """
    mount_dest = self.config_dict['mounts']['root']['destination']
    out = [f"echo 'Checking root mount: {mount_dest}'"]
    out += [f"if grep -q ' {mount_dest} ' /proc/mounts ; then"]
    out += ["    clean_mounts"]
    out += [f"    exec switch_root {mount_dest} /sbin/init"]
    out += ["else"]
    out += ["    echo 'Root mount not found, starting bash shell'"]
    out += ["fi"]

    return out

