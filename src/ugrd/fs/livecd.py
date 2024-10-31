__author__ = "desultory"
__version__ = "0.5.0"

from zenlib.util import contains


@contains("livecd_label", "livecd_label must be set to the label of the livecd.", raise_exception=True)
def generate_livecd_mount(self):
    """Makes the mounts entry for livecd base."""
    self["mounts"] = {"livecd": {"label": self.livecd_label, "no_validate": True}}


def prepare_squashfs_mount(self) -> str:
    """Create the folder for the squashfs mount in /run"""
    return "edebug $(mkdir -pv /run/squashfs)"


@contains("squashfs_image", "squashfs_image must be set to the path of the squashfs image to mount.", raise_exception=True)
def set_squashfs_mount(self):
    """Updates the root mount entry to use the squashfs image."""
    self["mounts"] = {
        "root": {
            "type": "squashfs",
            "options": ["loop"],
            "path": f"/livecd/{self.squashfs_image}",
            "destination": "/run/squashfs",
            "no_validate": True,
        }
    }
