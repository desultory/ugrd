__author__ = 'desultory'
__version__ = '2.5.0'

from importlib.metadata import version


def _process_switch_root_target(self, target) -> None:
    """ Processes the switch_root_target variable, masks the export_mount_info function. """
    dict.__setitem__(self, 'switch_root_target', target)
    self['masks'] = {'init_premount': 'export_mount_info', 'init_mount': 'mount_root'}
    self['imports'] = {'functions': {'ugrd.fs.mounts': ['mount_root']}}
    self['paths'] = target
    self['mounts'] = {'root': {'destination': target}}


def export_switchroot_target(self) -> str:
    """ Returns bash to export the switch_root_target variable to MOUNTS_ROOT_PATH, update the mounts dict so the fstab is accurate """
    if target := self.get('switch_root_target'):
        return f'export MOUNTS_ROOT_PATH={target}'
    else:
        self.logger.debug('No switch_root_target found, skipping export')


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

