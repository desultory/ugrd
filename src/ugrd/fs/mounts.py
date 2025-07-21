__author__ = "desultory"
__version__ = "7.1.4"

from pathlib import Path
from re import search
from typing import Union

from ugrd.exceptions import AutodetectError, ValidationError
from zenlib.util import colorize as c_
from zenlib.util import contains, pretty_print

BLKID_FIELDS = ["uuid", "partuuid", "label", "type"]
SOURCE_TYPES = ["uuid", "partuuid", "label", "path"]
MOUNT_PARAMETERS = [
    "destination",
    "source",
    "type",
    "options",
    "no_validate",
    "no_validate_options",
    "no_umount",
    "base_mount",
    *SOURCE_TYPES,
]

# Filesysms types where options should be inherited from active mounts, other than 'rw'
MOUNT_INHERIT_OPTIONS = ["f2fs"]


def _get_device_id(device: str) -> str:
    """Gets the device id from the device path."""
    return Path(device).stat().st_rdev >> 8, Path(device).stat().st_rdev & 0xFF


def _resolve_dev(self, device_path) -> str:
    """Resolves a device to one indexed in blkid.

    Takes the device path, such as /dev/root, and resolves it to a device indexed in blkid.
    If the device is an overlayfs, resolves the lowerdir device.

    If the device is a ZFS device, returns the device path.
    """
    if str(device_path) in self["_blkid_info"]:
        self.logger.debug("Device already resolved to blkid indexed device: %s" % device_path)
        return device_path

    self.logger.debug("Resolving device: %s" % device_path)
    mountpoint = _resolve_device_mountpoint(self, device_path)
    device_path = _resolve_overlay_lower_device(self, mountpoint)
    mountpoint = _resolve_device_mountpoint(self, device_path)  # May have changed if it was an overlayfs

    if self["_mounts"][mountpoint]["fstype"] == "zfs":
        self.logger.info("Resolved ZFS device: %s" % c_(device_path, "cyan"))
        return device_path

    mount_dev = self["_mounts"][mountpoint]["device"]
    major, minor = _get_device_id(mount_dev.split(":")[0] if ":" in mount_dev else mount_dev)

    for device in self["_blkid_info"]:
        check_major, check_minor = _get_device_id(device)
        if (major, minor) == (check_major, check_minor):
            self.logger.info("Resolved device: %s -> %s" % (c_(device_path, "blue"), c_(device, "cyan")))
            return device
    self.logger.critical("Failed to resolve device: %s" % c_(device_path, "red", bold=True))
    self.logger.error("Blkid info: %s" % pretty_print(self["_blkid_info"]))
    self.logger.error("Mount info: %s" % pretty_print(self["_mounts"]))
    return device_path


def _find_mountpoint(self, path: str) -> str:
    """Finds the mountpoint of a file or directory,
    Checks if the parent dir is a mountpoint, if not, recursively checks the parent dir."""
    check_path = Path(path).resolve()
    parent = check_path.parent if not check_path.is_dir() else check_path
    if str(parent) in self["_mounts"]:
        return str(parent)
    elif parent == Path("/"):  # The root mount SHOULD always be found...
        raise AutodetectError("Mountpoint not found for: %s" % path)
    return _find_mountpoint(self, parent.parent)


def _resolve_device_mountpoint(self, device) -> str:
    """Gets the mountpoint of a device based on the device path."""
    for mountpoint, mount_info in self["_mounts"].items():
        if str(device) == mount_info["device"]:
            return mountpoint
    self.logger.error("Mount info:\n%s" % pretty_print(self["_mounts"]))
    raise AutodetectError("Device mountpoint not found: %s" % repr(device))


def _resolve_overlay_lower_dir(self, mountpoint) -> str:
    for option in self["_mounts"][mountpoint]["options"]:
        if option.startswith("lowerdir="):
            return option.removeprefix("lowerdir=")
    raise AutodetectError(
        "[%s] No lower overlayfs mountpoint found: %s" % mountpoint, self["_mounts"][mountpoint]["options"]
    )


def _resolve_overlay_lower_device(self, mountpoint) -> dict:
    """Returns device for the lower overlayfs mountpoint.
    If it's not an overlayfs, returns the device for the mountpoint.

    If it is, iterate through the lowerdir devices until a non-overlayfs mount is found.
    """
    if self["_mounts"][mountpoint]["fstype"] != "overlay":
        return self["_mounts"][mountpoint]["device"]

    while self["_mounts"][mountpoint]["fstype"] == "overlay":
        lowerdir = _resolve_overlay_lower_dir(self, mountpoint)
        mountpoint = _find_mountpoint(self, lowerdir)
        if mountpoint == "/":  # The lowerdir mount should never be the root mount
            raise AutodetectError(f"[{mountpoint}] Lowerdir mount cannot be '/': {lowerdir}")

    return self["_mounts"][mountpoint]["device"]


def _get_mount_dev_fs_type(self, device: str, raise_exception=True) -> str:
    """Taking the device of an active mount, returns the filesystem type."""
    for info in self["_mounts"].values():
        if info["device"] == device:
            return info["fstype"]
    if not device.startswith("/dev/"):
        # Try again with /dev/ prepended if it wasn't already
        return _get_mount_dev_fs_type(self, f"/dev/{device}", raise_exception)

    if raise_exception:
        raise ValueError("No mount found for device: %s" % device)
    else:
        self.logger.debug("No mount found for device: %s" % device)


def _get_mount_source(self, mount: dict) -> str:
    """Gets the source from the mount config.
    Uses the order of SOURCE_TYPES to determine the source type.
        uuid, partuuid, label, path.

    Returns the source type and value if found, otherwise raises a ValueError.
    """
    for source_type in SOURCE_TYPES:
        if source_type in mount:
            return source_type, mount[source_type]
    raise ValueError("No source type found in mount: %s" % mount)


def _merge_mounts(self, mount_name: str, mount_config, mount_class) -> None:
    """Merges the passed mount config with the existing mount."""
    if mount_name not in self[mount_class]:
        self.logger.debug("[%s] Skipping mount merge, mount not found: %s" % (mount_class, mount_name))
        return mount_config

    self.logger.info("[%s] Updating mount: %s" % (c_(mount_class, bold=True), c_(mount_name, "blue")))
    self.logger.debug("[%s] Updating mount with: %s" % (mount_name, mount_config))
    if "options" in self[mount_class][mount_name] and "options" in mount_config:
        self.logger.debug("Merging options: %s" % mount_config["options"])
        self[mount_class][mount_name]["options"] = self[mount_class][mount_name]["options"] | set(
            mount_config["options"]
        )
        mount_config.pop("options")

    return dict(self[mount_class][mount_name], **mount_config)


@contains("validate", "Skipping mount validation, validation is disabled.", log_level=30)
def _validate_mount_config(self, mount_name: str, mount_config) -> None:
    """Validate the mount config."""
    if mount_config.get("no_validate"):
        return self.logger.warning("Skipping mount validation: %s" % c_(mount_name, "yellow", bold=True))

    for source_type in SOURCE_TYPES:
        if source_type in mount_config:
            self.logger.debug("[%s] Validated source type: %s" % (mount_name, mount_config))
            break
    else:  # If no source type is found, raise an error, unless it's the root mount
        if source_type not in mount_config and mount_name != "root":
            raise ValidationError("[%s] No source type found in mount: %s" % (mount_name, mount_config))

    for parameter, value in mount_config.copy().items():
        self.logger.debug("[%s] Validating parameter: %s" % (mount_name, parameter))
        if parameter == "options" and not mount_config.get("no_validate_options"):
            for option in value:
                if "subvol=" in option:
                    if mount_name == "root":
                        raise ValidationError(
                            "Please use the root_subvol parameter instead of setting the subvol option manually in the root mount."
                        )
                    elif mount_config["type"] not in ["btrfs", "bcachefs"]:
                        raise ValidationError("subvol option can only be used with btrfs or bcachefs mounts.")
        elif parameter not in MOUNT_PARAMETERS:
            raise ValueError("Invalid parameter in mount: %s" % parameter)


def _process_mount(self, mount_name: str, mount_config, mount_class="mounts") -> None:
    """Processes the passed mount config."""
    mount_config = _merge_mounts(self, mount_name, mount_config, mount_class)
    _validate_mount_config(self, mount_name, mount_config)

    # Set defaults
    mount_config["destination"] = Path(mount_config.get("destination", mount_name))
    if not mount_config["destination"].is_absolute():
        mount_config["destination"] = "/" / mount_config["destination"]
    mount_config["base_mount"] = mount_config.get("base_mount", False)
    mount_config["options"] = set(mount_config.get("options", ""))

    # Add imports based on the mount type
    if mount_type := mount_config.get("type"):
        if mount_type in ["vfat", "xfs"]:
            self["kmod_init"] = mount_type
        elif mount_type == "nilfs2":
            self["binaries"] = "mount.nilfs2"
        elif mount_type == "ext4":
            if "ugrd.fs.ext4" not in self["modules"]:
                self.logger.info("Auto-enabling module: %s", c_("ext4", "cyan"))
                self["modules"] = "ugrd.fs.ext4"
        elif mount_type == "f2fs":
            if "ugrd.fs.f2fs" not in self["modules"]:
                self.logger.info("Auto-enabling module: %s", c_("f2fs", "cyan"))
                self["modules"] = "ugrd.fs.f2fs"
        elif mount_type == "btrfs":
            if "ugrd.fs.btrfs" not in self["modules"]:
                self.logger.info("Auto-enabling module: %s", c_("btrfs", "cyan"))
                self["modules"] = "ugrd.fs.btrfs"
        elif mount_type == "bcachefs":
            if "ugrd.fs.bcachefs" not in self["modules"]:
                self.logger.info("Auto-enabling module: %s", c_("bcachefs", "cyan"))
                self["modules"] = "ugrd.fs.bcachefs"
        elif mount_type == "zfs":
            if "ugrd.fs.zfs" not in self["modules"]:
                self.logger.info("Auto-enabling module: zfs")
                self["modules"] = "ugrd.fs.zfs"
                mount_config["options"].add("zfsutil")
        elif mount_type not in ["proc", "sysfs", "devtmpfs", "squashfs", "tmpfs", "devpts"]:
            self.logger.warning("Unknown mount type: %s" % c_(mount_type, "red", bold=True))

    self[mount_class][mount_name] = mount_config
    self.logger.debug("[%s] Added mount: %s" % (mount_name, mount_config))

    if mount_class == "mounts":
        # Define the mountpoint path for standard mounts
        self["paths"] = mount_config["destination"]


def _process_mounts_multi(self, mount_name: str, mount_config) -> None:
    _process_mount(self, mount_name, mount_config)


def _process_late_mounts_multi(self, mount_name: str, mount_config) -> None:
    _process_mount(self, mount_name, mount_config, "late_mounts")


def _get_mount_str(self, mount: dict, pad=False, pad_size=44) -> str:
    """returns the mount source string based on the config,
    the output string should work with fstab and mount commands.
    pad: pads the output string with spaces, defined by pad_size (44)."""
    mount_type, mount_val = _get_mount_source(self, mount)
    out_str = mount_val if mount_type == "path" else f"{mount_type.upper()}={mount_val}"

    if pad:
        if len(out_str) > pad_size:
            pad_size = len(out_str) + 1
        out_str = out_str.ljust(pad_size, " ")

    return out_str


def _to_mount_cmd(self, mount: dict, mkdir=False) -> str:
    """Prints the object as a mount command."""
    out = [f"if ! grep -qs {mount['destination']} /proc/mounts; then"]

    if mkdir:
        out += [f"    mkdir -p {mount['destination']} || rd_fail 'Failed to create mountpoint: {mount['destination']}'"]

    mount_command = f"mount {_get_mount_str(self, mount)} {mount['destination']}"
    if options := mount.get("options"):
        mount_command += f" --options {','.join(options)}"
    if mount_type := mount.get("type"):
        mount_command += f" -t {mount_type}"

    mount_command += f" || rd_fail 'Failed to mount: {mount['destination']}'"

    out += [f"    {mount_command}", "else", f"    ewarn 'Mount already exists, skipping: {mount['destination']}'", "fi"]

    return out


def _to_fstab_entry(self, mount: dict) -> str:
    """Prints the mount config as an fstab entry."""
    fs_type = mount.get("type", "auto")

    out_str = _get_mount_str(self, mount, pad=True)
    out_str += str(mount["destination"]).ljust(24, " ")
    out_str += fs_type.ljust(16, " ")

    if options := mount.get("options"):
        out_str += ",".join(options)
    return out_str


def generate_fstab(self, mount_class="mounts", filename="/etc/fstab") -> None:
    """Generates the fstab from the specified mounts.
    Adds fstab entries to the check_in_file, to ensure they exist in the final image.
    """
    fstab_info = [f"# UGRD Filesystem module v{__version__}"]

    for mount_name, mount_info in self[mount_class].items():
        if not mount_info.get("base_mount") and mount_name != "root":
            try:
                self.logger.debug("[%s] Adding fstab entry for: %s" % (mount_class, mount_name))
                fstab_info.append(_to_fstab_entry(self, mount_info))
            except KeyError:
                self.logger.warning("System mount info:\n%s" % pretty_print(self["_mounts"]))
                raise ValueError("[%s] Failed to add fstab entry for: %s" % (mount_class, mount_name))

    if len(fstab_info) > 1:
        self._write(filename, fstab_info)
        self["check_in_file"][filename] = fstab_info
    else:
        self.logger.debug(
            "[%s] No fstab entries generated for mounts: %s" % (mount_class, ", ".join(self[mount_class].keys()))
        )


def umount_fstab(self) -> list[str]:
    """Generates a function to unmount all mounts which are not base_mounts
    and do not have no_umount set"""
    mountpoints = []
    for mount_info in self["mounts"].values():
        if mount_info.get("base_mount") or mount_info.get("no_umount"):
            continue
        if str(mount_info.get("destination")) == str(self["mounts"]["root"]["destination"]):
            continue

        mountpoints.append(str(mount_info["destination"]))
    if not mountpoints:
        return []

    out = [f"einfo 'Unmounting filesystems: {', '.join(mountpoints)}'"]
    for mountpoint in mountpoints:
        out.append(f"umount {mountpoint} || ewarn 'Failed to unmount: {mountpoint}'")

    return out


def get_mounts_info(self) -> None:
    """Gets the mount info for all devices."""
    try:
        with open("/proc/mounts", "r") as mounts:
            for line in mounts:
                device, mountpoint, fstype, options, _, _ = line.split()
                self["_mounts"][mountpoint] = {"device": device, "fstype": fstype, "options": options.split(",")}
    except FileNotFoundError:
        self.logger.critical("Failed to get mount info, detection and validation may fail!!!")

    self.logger.debug("Mount info: %s" % pretty_print(self["_mounts"]))


@contains("hostonly", "Skipping blkid enumeration, hostonly mode is disabled.", log_level=30)
def get_blkid_info(self, device=None) -> dict:
    """Gets the blkid info for all devices if no device is passed.
    Gets the blkid info for the passed device if a device is passed.
    The info is stored in self['_blkid_info']."""

    try:
        if device:
            blkid_output = self._run(["blkid", device]).stdout.decode().strip()
        else:
            blkid_output = self._run(["blkid"]).stdout.decode().strip()
    except RuntimeError:
        self.logger.error("Blkid output: %s" % blkid_output)
        raise AutodetectError("Failed to get blkid info for: %s" % device)

    if not blkid_output:
        raise AutodetectError("Unable to get blkid info.")

    for device_info in blkid_output.split("\n"):
        dev, info = device_info.split(": ", 1)
        info = " " + info  # Add space to make regex consistent
        self["_blkid_info"][dev] = {}
        self.logger.debug("[%s] Processing blkid line: %s" % (dev, info))
        for field in BLKID_FIELDS:
            if match := search(f' {field.upper()}="(.+?)"', info):
                self["_blkid_info"][dev][field] = match.group(1)

    if device and not self["_blkid_info"][device]:
        raise ValueError("[%s] Failed to parse blkid info: %s" % (device, info))

    self.logger.debug("Blkid info: %s" % pretty_print(self["_blkid_info"]))
    return self["_blkid_info"][device] if device else self["_blkid_info"]


def get_zpool_info(self, poolname=None) -> Union[dict, None]:
    """Enumerates ZFS pools and devices, adds them to the zpools dict."""
    if poolname:  # If a pool name is passed, try to get the pool info
        if "/" in poolname:
            # If a dataset is passed, get the pool name only
            poolname = poolname.split("/")[0]
        if poolname in self["_zpool_info"]:
            return self["_zpool_info"][poolname]

    # Always try to get zpool info, but only raise an error if a poolname is passed or the ZFS module is enabled
    try:
        pool_info = self._run(["zpool", "list", "-vPH", "-o", "name"]).stdout.decode().strip().split("\n")
    except FileNotFoundError:
        if "ugrd.fs.zfs" not in self["modules"]:
            return self.logger.debug("ZFS pool detection failed, but ZFS module not enabled, skipping.")
        if poolname:
            raise AutodetectError("Failed to get zpool list for pool: %s" % c_(poolname, "red"))

    capture_pool = False
    for line in pool_info:
        if not capture_pool:
            poolname = line  # Get the pool name using the first line
            self["_zpool_info"][poolname] = {"devices": set()}
            capture_pool = True
            continue
        else:  # Otherwise, add devices listed in the pool
            if line[0] != "\t":
                capture_pool = False
                continue  # Keep going
            # The device name has a tab before it, and may have a space/tab after it
            device_name = line[1:].split("\t")[0].strip()
            self.logger.debug("[%s] Found ZFS device: %s" % (c_(poolname, "blue"), c_(device_name, "cyan")))
            self["_zpool_info"][poolname]["devices"].add(device_name)

    if poolname:  # If a poolname was passed, try return the pool info, raise an error if not found
        return self["_zpool_info"][poolname]


@contains("hostonly", "Skipping virtual block device enumeration, hostonly mode is disabled.", log_level=30)
def get_virtual_block_info(self):
    """Populates the virtual block device info. (previously device mapper only)
    Disables device mapper autodetection if no virtual block devices are found.
    """

    sys_block = Path("/sys/devices/virtual/block")

    if not sys_block.exists():
        self["autodetect_root_dm"] = False
        return self.logger.warning("Virtual block devices unavailable, disabling device mapper autodetection.")

    devices = []
    for virt_device in Path("/sys/devices/virtual/block").iterdir():
        if virt_device.name.startswith("dm-"):
            devices.append(virt_device)
        elif virt_device.name.startswith("md"):
            devices.append(virt_device)
            # Check for partitions under virt_device/md*p*
            for part in virt_device.glob(f"{virt_device.name}p*"):
                devices.append(part)

    if not devices:
        self["autodetect_root_dm"] = False
        return self.logger.warning("No virtual block devices found, disabling device mapper autodetection.")

    for virt_dev in devices:
        maj, minor = (virt_dev / "dev").read_text().strip().split(":")
        self["_vblk_info"][virt_dev.name] = {"major": maj, "minor": minor}

        for attr in ["holders", "slaves"]:
            # For mdraid partitions, get values from the parent md device
            if virt_dev.name.startswith("md") and "p" in virt_dev.name:
                target = virt_dev.parent / attr
            else:
                target = virt_dev / attr

            try:
                self["_vblk_info"][virt_dev.name][attr] = [val.name for val in target.iterdir()]
            except FileNotFoundError:
                self.logger.warning(f"[{virt_dev.name}] Failed to get attribute: {attr}")

        if (virt_dev / "dm").exists():
            self["_vblk_info"][virt_dev.name]["uuid"] = (virt_dev / "dm/uuid").read_text().strip()
        elif (virt_dev / "md").exists():
            self["_vblk_info"][virt_dev.name]["uuid"] = (virt_dev / "md/uuid").read_text().strip()
            self["_vblk_info"][virt_dev.name]["level"] = (virt_dev / "md/level").read_text().strip()
        elif virt_dev.name.startswith("md") and "p" in virt_dev.name:
            # Get the parent md device info
            self["_vblk_info"][virt_dev.name]["uuid"] = (virt_dev.parent / "md/uuid").read_text().strip()
            self["_vblk_info"][virt_dev.name]["level"] = (virt_dev.parent / "md/level").read_text().strip()
        else:
            raise AutodetectError("Unable to find device information for: %s" % virt_dev.name)

        try:
            self["_vblk_info"][virt_dev.name]["name"] = (virt_dev / "dm/name").read_text().strip()
        except FileNotFoundError:
            self.logger.warning("No device mapper name found for: %s" % c_(virt_dev.name, "red", bold=True))
            self["_vblk_info"][virt_dev.name]["name"] = virt_dev.name  # we can pretend

    if self["_vblk_info"]:
        self.logger.info("Found virtual block devices: %s" % c_(", ".join(self["_vblk_info"].keys()), "cyan"))
        self.logger.debug("Virtual block device info: %s" % pretty_print(self["_vblk_info"]))
    else:
        self.logger.debug("No virtual block devices found.")


@contains("hostonly", "Skipping device mapper autodetection, hostonly mode is disabled.", log_level=30)
def _autodetect_dm(self, mountpoint, device=None) -> None:
    """Autodetects device mapper config given a mountpoint.
    Uses the mountpouint from self['_mounts'], raises an error if not found.
    Uses the device path if passed.
    Attempts to get the device info from blkid based on the device path.

    Ensures it's a device mapper mount, then autodetects the mount type.
    Adds kmods to the autodetect list based on the mount source.
    """
    if device:
        self.logger.debug("[%s] Using provided device for mount autodetection: %s" % (mountpoint, device))
        source_device = device
    elif mountpoint:
        source_device = _resolve_overlay_lower_device(self, mountpoint)
    else:
        raise AutodetectError("Mountpoint not found in host mounts: %s" % mountpoint)

    device_name = source_device.split("/")[-1]
    if not any(device_name.startswith(prefix) for prefix in ["dm-", "md"]):
        if not source_device.startswith("/dev/mapper/"):
            self.logger.debug("Mount is not a device mapper mount: %s" % source_device)
            return

    if source_device not in self["_blkid_info"]:
        if device_name in self["_vblk_info"]:
            source_name = self["_vblk_info"][device_name]["name"]
            if f"/dev/{source_name}" in self["_blkid_info"]:
                source_device = f"/dev/{source_name}"
            elif f"/dev/mapper/{source_name}" in self["_blkid_info"]:
                source_device = f"/dev/mapper/{source_name}"
            elif not get_blkid_info(self, source_device):
                raise AutodetectError("[%s] No blkid info for virtual device: %s" % (mountpoint, source_device))
        else:
            raise AutodetectError("[%s] No blkid info for virtual device: %s" % (mountpoint, source_device))

    self.logger.info("[%s] Detected virtual block device: %s" % (c_(mountpoint, "blue"), c_(source_device, "cyan")))
    source_device = Path(source_device)
    major, minor = _get_device_id(source_device)
    self.logger.debug("[%s] Major: %s, Minor: %s" % (source_device, major, minor))

    for name, info in self["_vblk_info"].items():
        if info["major"] == str(major) and info["minor"] == str(minor):
            dev_name = name
            break
    else:
        raise AutodetectError(
            "[%s] Unable to find device mapper device with maj: %s min: %s" % (source_device, major, minor)
        )

    if len(self["_vblk_info"][dev_name]["slaves"]) == 0:
        raise AutodetectError("No slaves found for device mapper device, unknown type: %s" % source_device.name)
    slave_source = self["_vblk_info"][dev_name]["slaves"][0]
    autodetect_mount_kmods(self, slave_source)

    try:
        blkid_info = self["_blkid_info"][f"/dev/{slave_source}"]
    except KeyError:
        if slave_source in self["_vblk_info"]:
            blkid_info = self["_blkid_info"][f"/dev/mapper/{self['_vblk_info'][slave_source]['name']}"]
        else:
            return self.logger.warning(f"No blkid info found for device mapper slave: {c_(slave_source, 'yellow')}")
    if source_device.name != self["_vblk_info"][dev_name]["name"] and source_device.name != dev_name:
        raise ValidationError(
            "Device mapper device name mismatch: %s != %s" % (source_device.name, self["_vblk_info"][dev_name]["name"])
        )

    self.logger.debug(
        "[%s] Device mapper info: %s\nDevice config: %s"
        % (source_device.name, self["_vblk_info"][dev_name], blkid_info)
    )
    if blkid_info.get("type") == "crypto_LUKS" or source_device.name in self.get("cryptsetup", {}):
        autodetect_luks(self, source_device, dev_name, blkid_info)
    elif blkid_info.get("type") == "LVM2_member":
        autodetect_lvm(self, source_device, dev_name, blkid_info)
    elif blkid_info.get("type") == "linux_raid_member":
        autodetect_raid(self, source_device, dev_name, blkid_info)
    else:
        if "type" not in blkid_info:
            self.logger.error(
                "If LUKS headers are detached, they must be configured with the corresponding mapped device name."
            )
            raise AutodetectError("[%s] No type found for device mapper device: %s" % (dev_name, source_device))
        raise ValidationError("Unknown device mapper device type: %s" % blkid_info.get("type"))

    for slave in self["_vblk_info"][dev_name]["slaves"]:
        try:
            _autodetect_dm(self, mountpoint, slave)  # Just pass the slave device name, as it will be re-detected
            self.logger.info(
                "[%s] Autodetected device mapper container: %s"
                % (c_(source_device.name, "blue", bright=True), c_(slave, "cyan"))
            )
        except KeyError:
            self.logger.debug("Slave does not appear to be a DM device: %s" % slave)


@contains("autodetect_root_raid", "Skipping RAID autodetection, autodetect_root_raid is disabled.", log_level=30)
@contains("hostonly", "Skipping RAID autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_raid(self, source_dev, dm_name, blkid_info) -> None:
    """Autodetects MD RAID mounts and sets the raid config.
    Adds kmods for the raid level to the autodetect list.
    """
    if "ugrd.fs.mdraid" not in self["modules"]:
        self.logger.info("Autodetected MDRAID mount, enabling the %s module." % c_("mdraid", "cyan"))
        self["modules"] = "ugrd.fs.mdraid"

    if level := self["_vblk_info"][dm_name].get("level"):
        self.logger.info("[%s] MDRAID level: %s" % (source_dev.name, c_(level, "cyan")))
        self["_kmod_auto"] = level
    else:
        raise AutodetectError("[%s] Failed to autodetect MDRAID level: %s" % (dm_name, blkid_info))


@contains("autodetect_root_lvm", "Skipping LVM autodetection, autodetect_root_lvm is disabled.", log_level=20)
@contains("hostonly", "Skipping LVM autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_lvm(self, source_dev, dm_num, blkid_info) -> None:
    """Autodetects LVM mounts and sets the lvm config."""
    if "ugrd.fs.lvm" not in self["modules"]:
        self.logger.info("Autodetected LVM mount, enabling the %s module." % c_("lvm", "cyan"))
        self["modules"] = "ugrd.fs.lvm"

    lvm_config = {}
    if uuid := blkid_info.get("uuid"):
        self.logger.info(
            "[%s] LVM volume contianer uuid: %s" % (c_(source_dev.name, "blue", bright=True), c_(uuid, "cyan"))
        )
        lvm_config["uuid"] = uuid
    else:
        raise AutodetectError("Failed to autodetect LVM volume uuid for device: %s" % c_(source_dev.name, "red"))

    if holders := self["_vblk_info"][dm_num]["holders"]:
        lvm_config["holders"] = holders

    self["lvm"] = {source_dev.name: lvm_config}


@contains("autodetect_root_luks", "Skipping LUKS autodetection, autodetect_root_luks is disabled.", log_level=30)
@contains("hostonly", "Skipping LUKS autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_luks(self, source_dev, dm_num, blkid_info) -> None:
    """Autodetects LUKS mounts and sets the cryptsetup config."""
    if "ugrd.crypto.cryptsetup" not in self["modules"]:
        self.logger.info("Autodetected LUKS mount, enabling the cryptsetup module: %s" % c_(source_dev.name, "cyan"))
        self["modules"] = "ugrd.crypto.cryptsetup"

    if "cryptsetup" in self and any(
        mount_type in self["cryptsetup"].get(self["_vblk_info"][dm_num]["name"], []) for mount_type in SOURCE_TYPES
    ):
        self.logger.warning(
            "Skipping LUKS autodetection, cryptsetup config already set: %s"
            % pretty_print(self["cryptsetup"][self["_vblk_info"][dm_num]["name"]])
        )
        return

    if len(self["_vblk_info"][dm_num]["slaves"]) > 1:
        self.logger.error("Device mapper slaves: %s" % c_(self["_vblk_info"][dm_num]["slaves"], "red", bold=True))
        raise AutodetectError("Multiple slaves found for device mapper device, unknown type: %s" % source_dev.name)

    dm_type = blkid_info.get("type")
    if dm_type != "crypto_LUKS":
        if not blkid_info.get("uuid"):  # No uuid will be defined if there are detached headers
            if not self["cryptsetup"][source_dev.name].get("header_file"):
                raise AutodetectError("[%s] Unknown LUKS mount type: %s" % (source_dev.name, dm_type))
        else:  # If there is some uuid and it's not LUKS, that's a problem
            raise AutodetectError(
                "[%s] Unknown device mapper slave type: %s" % (self["_vblk_info"][dm_num]["slaves"][0], dm_type)
            )

    # Configure cryptsetup based on the LUKS mount
    if uuid := blkid_info.get("uuid"):
        self.logger.info("[%s] LUKS volume uuid: %s" % (c_(source_dev.name, "blue", bright=True), c_(uuid, "cyan")))
        self["cryptsetup"] = {self["_vblk_info"][dm_num]["name"]: {"uuid": uuid}}
    elif partuuid := blkid_info.get("partuuid"):
        self.logger.info(
            "[%s] LUKS volume partuuid: %s" % (c_(source_dev.name, "blue", bright=True), c_(partuuid, "cyan"))
        )
        self["cryptsetup"] = {self["_vblk_info"][dm_num]["name"]: {"partuuid": partuuid}}

    self.logger.info(
        "[%s] Configuring cryptsetup for LUKS mount (%s) on: %s\n%s"
        % (
            c_(source_dev.name, "blue", bright=True),
            c_(self["_vblk_info"][dm_num]["name"], "cyan"),
            c_(dm_num, "blue"),
            pretty_print(self["cryptsetup"]),
        )
    )


@contains("hostonly", "Skipping init mount autodetection, hostonly mode is disabled.", log_level=30)
@contains("autodetect_init_mount", "Init mount autodetection disabled, skipping.", log_level=30)
@contains("init_target", "init_target must be set", raise_exception=True)
def autodetect_init_mount(self) -> None:
    """Checks the parent directories of init_target, if the path is a mountpoint, add it to late_mounts."""
    for mountpoint in ["/usr", "/var", "/etc"]:
        _autodetect_mount(self, mountpoint, "late_mounts", missing_ok=True)

    init_mount = _find_mountpoint(self, self["init_target"])
    if init_mount == "/":
        return

    if init_mount in self["late_mounts"]:
        return self.logger.debug("Init mount already detected: %s" % init_mount)

    if init_mount not in self["_mounts"]:
        raise AutodetectError("Init mount not found in host mounts: %s" % init_mount)

    self.logger.info("Detected init mount: %s" % c_(init_mount, "cyan"))
    _autodetect_mount(self, init_mount, "late_mounts")


@contains("autodetect_root", "Skipping root autodetection, autodetect_root is disabled.", log_level=30)
@contains("hostonly", "Skipping root autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_root(self) -> None:
    """Sets self['mounts']['root']'s source based on the host mount."""
    if "/" not in self["_mounts"]:
        self.logger.error("Host mounts:\n%s" % pretty_print(self["_mounts"]))
        raise AutodetectError(
            "Root mount not found in host mounts.\nCurrent mounts: %s" % pretty_print(self["_mounts"])
        )
    root_dev = _autodetect_mount(self, "/")
    if self["autodetect_root_dm"]:
        if self["mounts"]["root"]["type"] == "btrfs":
            from ugrd.fs.btrfs import _get_btrfs_mount_devices

            # Btrfs volumes may be backed by multiple dm devices
            for device in _get_btrfs_mount_devices(self, "/", root_dev):
                _autodetect_dm(self, "/", device)
        elif self["mounts"]["root"]["type"] == "zfs":
            for device in get_zpool_info(self, root_dev)["devices"]:
                _autodetect_dm(self, "/", device)
        else:
            _autodetect_dm(self, "/")


def _autodetect_mount(self, mountpoint, mount_class="mounts", missing_ok=False) -> str:
    """Sets mount config for the specified mountpoint, in the specified mount class.

    Returns the "real" device path for the mountpoint.
    """
    if mountpoint not in self["_mounts"]:
        if missing_ok:
            return self.logger.debug("Mountpoint not found in host mounts: %s" % mountpoint)
        self.logger.error("Host mounts:\n%s" % pretty_print(self["_mounts"]))
        raise AutodetectError("auto_mount mountpoint not found in host mounts: %s" % mountpoint)

    mountpoint_device = self["_mounts"][mountpoint]["device"]
    # get the fs type from the device as it appears in /proc/mounts
    fs_type = _get_mount_dev_fs_type(self, mountpoint_device, raise_exception=False)
    # resolve the device down to the "real" device path, one that has blkid info
    mount_device = _resolve_dev(self, mountpoint_device)
    # blkid may need to be re-run if the mount device is not in the blkid info
    # zfs devices are not in blkid, so we don't need to check for them
    if fs_type == "zfs":
        mount_info = {"type": "zfs", "path": mount_device}
    else:
        mount_info = get_blkid_info(self, mount_device)  # Raises an exception if the device is not found

    if ":" in mount_device:  # Handle bcachefs
        for alt_devices in mount_device.split(":"):
            autodetect_mount_kmods(self, alt_devices)
        mount_device = mount_device.split(":")[0]
    else:
        autodetect_mount_kmods(self, mount_device)

    # force the name "root" for the root mount, remove the leading slash for other mounts
    mount_name = "root" if mountpoint == "/" else mountpoint.removeprefix("/")

    # Don't overwrite existing mounts if a source type is already set
    if mount_name in self[mount_class] and any(s_type in self[mount_class][mount_name] for s_type in SOURCE_TYPES):
        return self.logger.warning(
            "[%s] Skipping autodetection, mount config already set:\n%s"
            % (c_(mountpoint, "yellow"), pretty_print(self[mount_class][mount_name]))
        )

    # Attempt to get the fs type, use auto if not found
    fs_type = mount_info.get("type", fs_type) or "auto"
    if fs_type == "auto":
        self.logger.warning("Failed to autodetect mount type for mountpoint:" % (c_(mountpoint, "yellow")))
    else:
        self.logger.info(
            "[%s] Autodetected mount type from device: %s" % (c_(mount_device, "blue"), c_(fs_type, "cyan"))
        )
    # Get mount options based on the mount tyoe
    if mount_class == "mounts":
        # Inherit mount options from the host mount for certain mount types
        if fs_type in MOUNT_INHERIT_OPTIONS:
            mount_options = self["_mounts"][mountpoint].get("options", ["ro"])
            if 'rw' in mount_options:
                mount_options.pop(mount_options.index("rw"))  # Remove rw option if it exists
        else:  # For standard mounts, default ro
            mount_options = ["ro"]
    else:  # For other mounts, use the existing mount config
        mount_options = self["_mounts"][mountpoint].get("options", ["default"])

    mount_config = {mount_name: {"options": mount_options, "type": fs_type.lower()}}

    for source_type in SOURCE_TYPES:
        if source := mount_info.get(source_type):
            self.logger.info(
                "[%s] Autodetected mount source: %s=%s"
                % (c_(mount_name, "blue", bright=True), c_(source_type, "blue"), c_(source, "cyan"))
            )
            mount_config[mount_name][source_type] = source
            break
    else:
        if fs_type != "zfs":  # For ZFS, the source is the pool name
            raise AutodetectError("[%s] Failed to autodetect mount source." % mountpoint)

    # for zfs mounts, set the path to the pool name
    if fs_type == "zfs":
        mount_config[mount_name]["path"] = mount_device

    self[mount_class] = mount_config
    return mount_device


@contains("auto_mounts", "Skipping auto mounts, auto_mounts is empty.", log_level=10)
@contains("hostonly", "Skipping mount autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_mounts(self) -> None:
    """Configured the mount config for a device based on the host mount config."""
    for mountpoint in self["auto_mounts"]:
        _autodetect_mount(self, mountpoint)


def mount_base(self) -> list[str]:
    """Generates mount commands for the base mounts.
    Must be run before variables are used, as it creates the /run/ugrd directory.
    """
    out = []
    for mount_name, mount_info in self["mounts"].items():
        if not mount_info.get("base_mount") or mount_name == "devpts":
            continue  # devpts must be mounted last, if needed
        out.extend(_to_mount_cmd(self, mount_info))

    if self["mount_devpts"]:
        out.extend(_to_mount_cmd(self, self["mounts"]["devpts"], mkdir=True))

    out += [f'einfo "Mounted base mounts, version: {__version__}"']
    return out


def _process_run_dirs_multi(self, run_dir: Union[str, Path]) -> None:
    """Processes run_dirs items.
    Ensures the path starts with /run, adds it if it does not"""
    run_dir = Path(run_dir)
    if run_dir.is_absolute():
        if run_dir.parts[1] == "run":
            pass
        run_dir = "/run" / run_dir.relative_to("/")
    else:
        run_dir = "/run" / run_dir
    self.data["run_dirs"].append(run_dir)


@contains("run_dirs")
def make_run_dirs(self) -> list[str]:
    """Generates commands to create the run directories."""
    return ['edebug Creating run dir: "$(mkdir -pv %s)"' % run_dir for run_dir in self["run_dirs"]]


@contains("late_mounts", "Skipping late mounts, late_mounts is empty.")
def mount_late(self) -> list[str]:
    """Generates mount commands for the late mounts."""
    target_dir = str(self["mounts"]["root"]["destination"])
    out = [f'einfo "Mounting late mounts at {target_dir}: {" ,".join(self["late_mounts"].keys())}"']
    for mount in self["late_mounts"].values():
        if not str(mount["destination"]).startswith(target_dir):
            mount["destination"] = Path(target_dir, str(mount["destination"]).removeprefix("/"))
        out += _to_mount_cmd(self, mount)
    return out


def mount_fstab(self) -> list[str]:
    """Generates the init function for mounting the fstab.
    Keeps re-attempting with mount_timeout until successful.
    mount_retries sets the number of times to retry the mount, infinite otherwise.
    """
    if not self._get_build_path("/etc/fstab").exists():
        return self.logger.info("No initramfs fstab found, skipping mount_fstab. If non-root storage devices are not needed at boot, this is fine.")

    out = [
        'einfo "Attempting to mount all filesystems."',
    ]

    if retries := self.get("mount_retries"):
        out += [
            f'retry {retries} "$(readvar ugrd_mount_timeout)" mount -a || rd_fail "Failed to mount all filesystems."',
        ]
    else:
        out += [
            "while ! mount -a; do",  # Retry forever, retry with a very short timeout may fail
            '    if prompt_user "Press space to break, waiting: $(readvar ugrd_mount_timeout)s" "$(readvar ugrd_mount_timeout)"; then',
            '        rd_fail "Failed to mount all filesystems. Process interrupted by user."',
            "    fi",
            '    eerror "Failed to mount all filesystems, retrying."',
            "done",
            "einfo 'All filesystems mounted.'",
        ]

    return out


def _validate_host_mount(self, mount, destination_path=None) -> bool:
    """Checks if a defined mount exists on the host."""
    if mount.get("no_validate"):
        return self.logger.warning("Skipping host mount validation for config:\n%s" % pretty_print(mount))
    if mount.get("base_mount"):
        return self.logger.debug("Skipping host mount validation for base mount: %s" % mount)

    mount_type, mount_val = _get_mount_source(self, mount)
    # If a destination path is passed, like for /, use that instead of the mount's destination
    destination_path = str(mount["destination"]) if destination_path is None else destination_path

    host_source_dev = _resolve_dev(self, self["_mounts"][destination_path]["device"])
    if ":" in host_source_dev:  # Handle bcachefs
        host_source_dev = host_source_dev.split(":")[0]

    host_mount_options = self["_mounts"][destination_path]["options"]
    for option in mount.get("options", []):
        if mount.get("no_validate_options"):
            break  # Skip host option validation if this is set
        if option == "ro":  # Allow the ro option to be set in the config
            continue
        if option == "zfsutil":
            if self["_mounts"][destination_path]["fstype"] == "zfs":
                continue
            raise ValueError("Cannot set 'zfsutil' option for non-zfs mount: %s" % destination_path)
        if option not in host_mount_options:
            raise ValidationError(
                "Host mount options mismatch. Expected: %s, Found: %s" % (mount["options"], host_mount_options)
            )

    if mount_type == "path":
        if mount_val == Path(host_source_dev) or mount_val == host_source_dev:
            self.logger.debug("[%s] Host mount validated: %s" % (destination_path, mount))
            return True
        raise ValidationError(
            "Host mount path device path does not match config. Expected: %s, Found: %s" % (mount_val, host_source_dev)
        )
    elif mount_type in ["uuid", "partuuid", "label"]:
        # For uuid, partuuid, and label types, check that the source matches the host mount
        if self["_blkid_info"][host_source_dev][mount_type] != mount_val:
            raise ValidationError(
                "Host mount source device mismatch. Expected: %s: %s, Found: %s"
                % (mount_type, mount_val, host_source_dev)
            )
        self.logger.debug("[%s] Host mount validated: %s" % (destination_path, mount))
        return True
    raise ValidationError("[%s] Unable to validate host mount: %s" % (destination_path, mount))


@contains("validate", "Skipping host mount validation, validation is disabled.", log_level=30)
def check_mounts(self) -> None:
    """Validates all mounts against the host mounts.
    For the 'root' mount, the destination path is set to '/'.
    """
    for mount_name, mount in self["mounts"].items():
        _validate_host_mount(self, mount, "/" if mount_name == "root" else None)


def mount_default_root(self) -> str:
    """Mounts the root partition to $MOUNTS_ROOT_TARGET."""
    return """
    mount_source=$(readvar MOUNTS_ROOT_SOURCE)
    mount_type=$(readvar MOUNTS_ROOT_TYPE auto)
    mount_options="$(readvar MOUNTS_ROOT_OPTIONS 'defaults,ro')$(readvar root_extra_options)"
    mount_target=$(readvar MOUNTS_ROOT_TARGET)
    if grep -qs "$mount_target" /proc/mounts; then
        ewarn "Root mount already exists, adding 'remount' option: $mount_options"
        mount_options="remount,$mount_options"
    fi
    einfo "[/] Mounting '$mount_source' ($mount_type) to '$mount_target' with options: $mount_options"
    while ! mount "$mount_source" -t "$mount_type" -o "$mount_options" "$mount_target"; do
        eerror "Failed to mount root partition."
        if prompt_user "Press space to break, waiting: $(readvar ugrd_mount_timeout)s" "$(readvar ugrd_mount_timeout)"; then
            rd_fail "Failed to mount root partition."
        fi
    done
    """


def mount_root(self) -> str:
    """Returns a shell script to mount the root partition.
    Uses root options defined in the cmdline if set, otherwise uses mount_default_root.
    """
    return """
    root=$(readvar root)
    if [ -z "$root" ]; then
        edebug "No root partition specified in /proc/cmdline, falling back to mount_root"
        mount_default_root
        return
    fi
    roottype="$(readvar roottype auto)"
    rootflags="$(readvar rootflags 'defaults,ro')"
    einfo "Mounting root partition based on /proc/cmdline: $root -t $roottype -o $rootflags"
    if ! mount "$root" "$(readvar MOUNTS_ROOT_TARGET)" -t "$roottype" -o "$rootflags"; then
        eerror "Failed to mount the root partition using /proc/cmdline: $root -t $roottype -o $rootflags"
        mount_default_root
    fi
    """


def export_mount_info(self) -> None:
    """Exports mount info based on the config to /run/MOUNTS_ROOT_{option}"""
    try:
        self["exports"]["MOUNTS_ROOT_SOURCE"] = _get_mount_str(self, self["mounts"]["root"])
    except ValueError as e:
        self.logger.critical(f"Failed to get source info for the root mount: {e}")
        if not self["hostonly"]:
            self.logger.info("Root mount infomrmation can be defined under the '[mounts.root]' section.")
            raise ValidationError("Root mount source information is not set, when hostonly mode is disabled, it must be manually defined.")
        raise ValidationError("Root mount source information is not set even though hostonly mode is enabled. Please report a bug.")
    self["exports"]["MOUNTS_ROOT_TYPE"] = self["mounts"]["root"].get("type", "auto")
    self["exports"]["MOUNTS_ROOT_OPTIONS"] = ",".join(self["mounts"]["root"]["options"])
    self["exports"]["MOUNTS_ROOT_TARGET"] = self["mounts"]["root"]["destination"]
    self["exports"]["ugrd_mount_timeout"] = self.get("mount_timeout", 1)


def autodetect_zfs_device_kmods(self, poolname) -> list[str]:
    """Gets kmods for all devices in a ZFS pool and adds them to _kmod_auto."""
    for device in get_zpool_info(self, poolname)["devices"]:
        if device_kmods := resolve_blkdev_kmod(self, device):
            self.logger.info(
                "[%s:%s] Auto-enabling kernel modules for ZFS device: %s"
                % (
                    c_(poolname, "blue", bright=True),
                    c_(device, "blue", bold=True),
                    c_(", ".join(device_kmods), "cyan"),
                )
            )
            self["_kmod_auto"] = device_kmods


def autodetect_mount_kmods(self, device) -> None:
    """Autodetects the kernel modules for a block device."""
    if fs_type := _get_mount_dev_fs_type(self, device, raise_exception=False):
        # This will fail for most non-zfs devices
        if fs_type == "zfs":
            return autodetect_zfs_device_kmods(self, device)

    if "/" not in str(device):
        device = f"/dev/{device}"

    if device_kmods := resolve_blkdev_kmod(self, device):
        self.logger.info(
            "[%s] Auto-enabling kernel modules for device: %s"
            % (c_(device, "blue"), c_(", ".join(device_kmods), "cyan"))
        )
        self["_kmod_auto"] = device_kmods


def resolve_blkdev_kmod(self, device) -> list[str]:
    """Gets the kmod name for a block device."""
    kmods = []
    dev = Path(device)
    while dev.is_symlink():
        dev = dev.resolve()

    if dev.is_block_device():
        major, minor = _get_device_id(device)
        sys_dev = str(Path(f"/sys/dev/block/{major}:{minor}").resolve())
        if "/usb" in sys_dev:
            if "ugrd.kmod.usb" not in self["modules"]:
                self.logger.info(
                    "Auto-enabling %s for USB device: %s" % (c_("ugrd.kmod.usb", bold=True), c_(device, "cyan"))
                )
                self["modules"] = "ugrd.kmod.usb"
    device_name = dev.name

    if device_name.startswith("dm-") or dev.parent.name == "mapper" or dev.parent.name.startswith("vg"):
        kmods.append("dm_mod")
    elif device_name.startswith("nvme"):
        kmods.append("nvme")
    elif device_name.startswith("vd"):
        kmods.append("virtio_blk")
    elif device_name.startswith("sd"):
        kmods.append("sd_mod")
        if self["virtual_machine"]:
            self.logger.info(f"Auto-enabling virtio_scsi for virtual machine block device: {c_(device_name, 'cyan')}")
            kmods.append("virtio_scsi")
    elif device_name.startswith("mmcblk"):
        kmods.append("mmc_block")
    elif device_name.startswith("sr"):
        kmods.append("sr_mod")
    elif device_name.startswith("md"):
        kmods.append("md_mod")
    else:
        self.logger.error(
            "[%s] Unable to determine kernel module for block device: %s" % (device_name, c_(device, "red", bold=True))
        )
    return kmods
