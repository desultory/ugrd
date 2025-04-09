__version__ = "0.1.1"

from zenlib.util import unset


@unset("no_fsck", "Not adding f2fs fsck as no_fsck is set", log_level=30)
def f2fs_fsck(self) -> str:
    """Returns a shell function to run fsck on the root filesystem
    The root device is determined by checking the source of SWITCH_ROOT_TARGET"""
    return """
    if check_var ugrd_no_fsck; then
        ewarn 'ugrd_no_fsck is set, skipping fsck'
        return
    fi
    ROOT_DEV=$(awk -v target="$(readvar SWITCH_ROOT_TARGET)" '$2 == target {{print $1}}' /proc/mounts)
    ROOT_TYPE=$(awk -v target="$(readvar SWITCH_ROOT_TARGET)" '$2 == target {{print $3}}' /proc/mounts)
    ROOT_OPTS=$(awk -v target="$(readvar SWITCH_ROOT_TARGET)" '$2 == target {{print $4}}' /proc/mounts)
    if [ "$ROOT_TYPE" != "f2fs" ]; then
        einfo 'Root filesystem is not f2fs, skipping fsck'
        return
    fi
    einfo Running fsck on: $ROOT_DEV
    umount $(readvar SWITCH_ROOT_TARGET) # Unmount the root filesystem so fsck can run
    einfo $(fsck.f2fs -f $ROOT_DEV)
    mount $ROOT_DEV $(readvar SWITCH_ROOT_TARGET) -o $ROOT_OPTS # Remount using the same options
    """
