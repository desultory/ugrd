__author__ = "desultory"
__version__ = "0.3.0"

from zenlib.util import contains


@contains("livecd_label", "livecd_label must be set to the label of the livecd.", raise_exception=True)
def generate_livecd_mount(self):
    """ Makes the mounts entry for livecd base. """
    self['mounts'] = {'livecd': {'label': self.livecd_label, 'no_validate': True}}


@contains("squashfs_image", "squashfs_image must be set to the path of the squashfs image to mount.", raise_exception=True)
def mount_squashfs(self):
    """
    Returns bash lines to mount squashfs image.
    Creates /run/squashfs directory to mount squashfs image.
    Creates /run/upperdir and /run/workdir directories for overlayfs.
    """
    return ["einfo $(mkdir -pv /run/squashfs)",
            f"mount -t squashfs -o loop /livecd/{self.squashfs_image} /run/squashfs || rd_fail 'Failed to mount squashfs image: {self.squashfs_image}'",
            "edebug $(mkdir -pv /run/upperdir)",
            "edebug $(mkdir -pv /run/workdir)",
            f"mount -t overlay overlay -o lowerdir=/run/squashfs,upperdir=/run/upperdir,workdir=/run/workdir {self.mounts['root']['destination']} || rd_fail 'Failed to mount overlayfs'"]
