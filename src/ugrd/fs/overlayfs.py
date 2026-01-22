__version__ = "0.4.0"

from zenlib.util import contains, unset


def update_root_lowerdir(self):
    """Updates the root mount to use the lowerdir,
    Sets the switch_root_target to /target_rootfs"""
    self["mounts"] = {"root": {"destination": "/run/lowerdir"}}
    self["switch_root_target"] = "/target_rootfs"


def add_overlayfs_rundirs(self):
    """Adds the directores needed for overlayfs to /run"""
    self["run_dirs"] = "lowerdir"
    if not self.get("livecd_persistence", False):
        self["run_dirs"] = ["workdir", "upperdir"]


@unset("livecd_persistence", "Livecd persistence is enabled, using persistent overlayfs", log_level=10)
def mount_overlayfs(self) -> str:
    """Returns shell lines to mount the overlayfs based on the defined lowerdir"""
    return 'edebug "Mounting overlayfs at $(readvar SWITCH_ROOT_TARGET)): $(mount -t overlay overlay -o lowerdir=/run/lowerdir,upperdir=/run/upperdir,workdir=/run/workdir "$(readvar SWITCH_ROOT_TARGET)")"'


@contains("livecd_persistence", "Livecd persistence is disabled, using a non-persistent overlayfs", log_level=10)
def mount_persistent_overlayfs(self) -> str:
    """Returns shell lines to make the upper/workdirs and mount the persistent overlayfs
    The root of the persistent overlayfs is mounted at /run/livecd/persistence

    Directores are created at /run/livecd/persistence/upperdir and /run/livecd/persistence/workdir

    """
    return """
    mkdir -p run/livecd_persistence/upperdir
    mkdir -p run/livecd_persistence/workdir

    edebug "Mounting persistent overlayfs at $(readvar SWITCH_ROOT_TARGET)): $(mount -t overlay overlay -o lowerdir=/run/lowerdir,upperdir=/run/livecd_persistence/upperdir,workdir=/run/livecd_persistence/workdir "$(readvar SWITCH_ROOT_TARGET)")"
    """
