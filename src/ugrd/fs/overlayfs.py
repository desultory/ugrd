__version__ = "0.2.0"


def update_root_lowerdir(self):
    """Updates the root mount to use the lowerdir,
    Sets the switch_root_target to /target_rootfs"""
    self['mounts'] = {'root': {'destination': '/run/lowerdir'}}
    self["switch_root_target"] = "/target_rootfs"


def init_overlayfs(self) -> str:
    """Returns bash lines to create the upperdir and workdir
    Uses /run/upperdir and /run/workdir."""
    return "edebug $(mkdir -pv /run/upperdir /run/workdir /run/lowerdir)"


def mount_overlayfs(self) -> str:
    """Returns bash lines to mount the overlayfs based on the defined lowerdir"""
    return 'edebug "Mounting overlayfs at $(readvar SWITCH_ROOT_TARGET)): $(mount -t overlay overlay -o lowerdir=/run/lowerdir,upperdir=/run/upperdir,workdir=/run/workdir $(readvar SWITCH_ROOT_TARGET))"'
