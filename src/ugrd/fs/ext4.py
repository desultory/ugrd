__version__ = "0.4.1"

from zenlib.util import unset


@unset("no_fsck", "Not adding ext4 fsck as no_fsck is set", log_level=30)
def ext4_fsck(self) -> str:
    """Returns a shell function to run fsck on the root filesystem
    The root device is determined by checking the source of SWITCH_ROOT_TARGET"""
    return """
    if check_var no_fsck; then
        ewarn 'no_fsck is set, skipping fsck'
        return
    fi
    ROOT_DEV=$(awk -v target="$(readvar SWITCH_ROOT_TARGET)" '$2 == target {{print $1}}' /proc/mounts)
    ROOT_TYPE=$(awk -v target="$(readvar SWITCH_ROOT_TARGET)" '$2 == target {{print $3}}' /proc/mounts)
    ROOT_OPTS=$(awk -v target="$(readvar SWITCH_ROOT_TARGET)" '$2 == target {{print $4}}' /proc/mounts)
    if [ "$ROOT_TYPE" != "ext4" ]; then
        einfo 'Root filesystem is not ext4, skipping fsck'
        return
    fi
    einfo Running fsck on: $ROOT_DEV
    umount $(readvar SWITCH_ROOT_TARGET) # Unmount the root filesystem so fsck can run
    einfo $(fsck.ext4 -p $ROOT_DEV)
    mount $ROOT_DEV $(readvar SWITCH_ROOT_TARGET) -o $ROOT_OPTS # Remount using the same options
    """
