__version__ = "1.12.3"
__author__ = "desultory"

from pathlib import Path

from ugrd import ValidationError
from ugrd.fs.mounts import _resolve_overlay_lower_dir
from zenlib.util import contains, unset


class SubvolNotFound(Exception):
    pass


class SubvolIsRoot(Exception):
    pass


def _get_btrfs_mount_devices(self, mountpoint: str, dev=None) -> list:
    """Returns a list of device paths for a btfrs mountpoint."""
    fs_dev = dev or self["_mounts"][mountpoint]["device"]
    fs_uuid = self["_blkid_info"][fs_dev]["uuid"]
    return [str(p.name) for p in Path(f"/sys/fs/btrfs/{fs_uuid}/devices").iterdir()]


def _get_mount_subvol(self, mountpoint: str) -> list:
    """Returns the subvolume name for a mountpoint."""
    if self["_mounts"][mountpoint]["fstype"] == "overlay":
        mountpoint = _resolve_overlay_lower_dir(self, mountpoint)
    elif self["_mounts"][mountpoint]["fstype"] != "btrfs":
        raise ValidationError("Mountpoint is not a btrfs mount: %s" % mountpoint)
    for option in self["_mounts"][mountpoint]["options"]:
        if option.startswith("subvol="):
            subvol = option.split("=")[1]
            if subvol == "/":
                raise SubvolIsRoot("Mount is at volume root: %s" % mountpoint)
            self.logger.debug("[%s] Detected subvolume: %s" % (mountpoint, subvol))
            return subvol
    raise SubvolNotFound("No subvolume detected.")


@contains("validate", "validate is not enabled, skipping root subvolume validation.")
def _validate_root_subvol(self) -> None:
    """Validates the root subvolume."""
    try:
        detected_subvol = _get_mount_subvol(self, "/")
    except SubvolNotFound:
        if self["root_subvol"]:
            raise ValidationError(
                "Current root mount is not using a subvolume, but root_subvol is set: %s" % self["root_subvol"]
            )
    except SubvolIsRoot:
        if self["root_subvol"] != "/":
            raise ValidationError(
                "Current root mount is not using a subvolume, but root_subvol is set: %s" % self["root_subvol"]
            )

    if self["root_subvol"] != detected_subvol:
        raise ValidationError(
            "[%s] Root subvolume does not match detected subvolume: %s" % (self["root_subvol"], detected_subvol)
        )


def _process_root_subvol(self, root_subvol: str) -> None:
    """processes the root subvolume."""
    self.data["root_subvol"] = root_subvol
    self.logger.debug("Set root_subvol to: %s", root_subvol)


def _process_subvol_selector(self, subvol_selector: bool) -> None:
    """Adds the base mount path to paths if subvol_selector is enabled."""
    if subvol_selector:
        self.data["subvol_selector"] = subvol_selector
        self.logger.debug("Set subvol_selector to: %s", subvol_selector)
        self["paths"] = self["_base_mount_path"]


def btrfs_scan(self) -> str:
    """scan for new btrfs devices."""
    return 'einfo "$(btrfs device scan)"'


@unset("subvol_selector", message="subvol_selector is enabled, skipping.", log_level=20)
@contains("autodetect_root_subvol", "autodetect_root_subvol is not enabled, skipping.", log_level=30)
@unset("root_subvol", message="root_subvol is set, skipping.")
@contains("hostonly", "hostonly is not enabled, skipping.", log_level=30)
def autodetect_root_subvol(self):
    """Detects the root subvolume."""
    try:
        root_subvol = _get_mount_subvol(self, "/")
        self.logger.info("Detected root subvolume: %s", root_subvol)
        self["root_subvol"] = root_subvol
    except SubvolNotFound:
        self.logger.warning("Failed to detect root subvolume.")
    except SubvolIsRoot:
        self.logger.debug("Root mount is not using a subvolume.")


@contains("subvol_selector", message="subvol_selector is not enabled, skipping.")
@unset("root_subvol", message="root_subvol is set, skipping.")
def select_subvol(self) -> str:
    """Returns a shell script to list subvolumes on the root volume."""
    # TODO: Figure out a way to make the case prompt more standard
    return f"""
    mount -t btrfs -o subvolid=5,ro $(readvar MOUNTS_ROOT_SOURCE) {self["_base_mount_path"]}
    if [ -z "$(btrfs subvolume list -o {self['_base_mount_path']})" ]; then
        ewarn "Failed to list btrfs subvolumes for root volume: {self['_base_mount_path']}"
    else
        echo 'Select a subvolume to use as root'
        PS3='Subvolume: '
        select subvol in $(btrfs subvolume list -o {self['_base_mount_path']} " + "| awk '{{print $9}}'); do
        case $subvol in
            *)
                if [[ -z $subvol ]]; then
                    ewarn 'Invalid selection'
                else
                    einfo "Selected subvolume: $subvol"
                    echo -n ",subvol=$subvol" >> /run/vars/MOUNTS_ROOT_OPTIONS
                    break
                fi
                ;;
            esac
        done
    fi
    umount -l {self['_base_mount_path']}
    """


@contains("root_subvol", message="root_subvol is not set, skipping.")
def set_root_subvol(self) -> str:
    """Adds the root_subvol to the root_mount options."""
    _validate_root_subvol(self)
    return f"""echo -n ",subvol={self['root_subvol']}" >> /run/vars/MOUNTS_ROOT_OPTIONS"""
