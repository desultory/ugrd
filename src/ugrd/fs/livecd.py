__author__ = "desultory"
__version__ = "0.7.0"

from zenlib.util import contains


@contains("livecd_label", "livecd_label must be set to the label of the livecd storage root.", raise_exception=True)
def mount_livecd(self) -> str:
    """Returns shell lines to mount the livecd storage root.
    exports the set livecd_label,
    if a livecd_label cmdline arg is passed, uses that value instead of the exported value

    Because this mount is made manulally, no mount entry/validation/unmounting is done
    All mount handling happens strictly at runtime
    """
    return f"""
    livecd_label="$(readvar ugrd_livecd_label)"
    if [ -z "$livecd_label" ]; then
        rd_fail "ugrd_livecd_label must be set to the label of the livecd storage root."
    fi
    einfo "Mounting livecd with label: $livecd_label"
    while ! mount LABEL="$livecd_label" /run/livecd 2>/dev/null; do
        eerror "Failed to mount livecd with label: $livecd_label"
        if prompt_user "Press enter to break, waiting: {self["mount_timeout"]}s" {self["mount_timeout"]}; then
            rd_fail "Failed to mount livecd with label: $livecd_label"
        fi
    done
    """


@contains("livecd_label", "livecd_label must be set to the label of the livecd storage root.", raise_exception=True)
@contains(
    "squashfs_image", "squashfs_image must be set to the path of the livecd squashfs image.", raise_exception=True
)
def set_livecd_mount(self):
    """Updates the root mount entry to use the squashfs image.
    Adds an export for the livecd_label.
    """
    self["mounts"] = {
        "root": {
            "type": "squashfs",
            "options": ["loop"],
            "path": f"/run/livecd/{self.squashfs_image}",
            "no_validate": True,
        }
    }
    self["exports"]["ugrd_livecd_label"] = self.livecd_label


def set_squashfs_root_source(self) -> str:
    """Returns shell lines to set MOUNTS_ROOT_SOURCE to the squashfs_image if set,
    otherwise checks that the built-in squashfs source exists."""
    return """
    root_source="$(readvar MOUNTS_ROOT_SOURCE)"
    squashfs_image_name="$(readvar squashfs_image)"
    squashfs_image="/run/livecd/$squashfs_image_name"
    if [ -n "$squashfs_image_name" ]; then
        if [ -e "$squashfs_image" ]; then
            einfo "Using squashfs image set by the kernel commandline: $squashfs_image"
            setvar MOUNTS_ROOT_SOURCE "$squashfs_image"
            return
        else
            ewarn "Squashfs image does not exist: $squashfs_image"
        fi
    fi
    if [ -e "$root_source" ]; then
        einfo "Using squashfs image set in MOUNTS_ROOT_SOURCE: $root_source"
    else
        rd_fail "Squashfs image does not exist: $squashfs_image"
    fi
    """

