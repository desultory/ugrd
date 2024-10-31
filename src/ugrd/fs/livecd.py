__author__ = "desultory"
__version__ = "0.5.2"

from zenlib.util import contains


@contains("livecd_label", "livecd_label must be set to the label of the livecd.", raise_exception=True)
def generate_livecd_mount(self):
    """Makes the mounts entry for livecd base."""
    self["mounts"] = {
        "livecd": {
            "label": self.livecd_label,
            "destination": "/run/livecd",
            "no_validate": True,
            "no_umount": True,
            "options": ["ro"],
        }
    }


@contains("squashfs_image", "squashfs_image must be set to the path of the squashfs image to mount.", raise_exception=True)
def set_squashfs_mount(self):
    """Updates the root mount entry to use the squashfs image."""
    self["mounts"] = {
        "root": {
            "type": "squashfs",
            "options": ["loop"],
            "path": f"/run/livecd/{self.squashfs_image}",
            "no_validate": True,
        }
    }

def init_livecd(self):
    return "mkdir -p /run/livecd"
