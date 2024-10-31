__version__ = "0.3.0"


def update_root_lowerdir(self):
    """Updates the root mount to use the lowerdir,
    Sets the switch_root_target to /target_rootfs"""
    self['mounts'] = {'root': {'destination': '/run/lowerdir'}}
    self["switch_root_target"] = "/target_rootfs"


def mount_overlayfs(self) -> str:
    """Returns bash lines to mount the overlayfs based on the defined lowerdir"""
    return 'edebug "Mounting overlayfs at $(readvar SWITCH_ROOT_TARGET)): $(mount -t overlay overlay -o lowerdir=/run/lowerdir,upperdir=/run/upperdir,workdir=/run/workdir "$(readvar SWITCH_ROOT_TARGET)")"'
