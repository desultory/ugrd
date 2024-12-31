__author__ = "desultory"
__version__ = "6.0.0"

from pathlib import Path
from typing import Union

from ugrd import AutodetectError, ValidationError
from zenlib.util import colorize, contains, pretty_print

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


@contains("validate", "Skipping mount validation, validation is disabled.", log_level=30)
def _validate_mount_config(self, mount_name: str, mount_config) -> None:
    """Validate the mount config."""
    if mount_config.get("no_validate"):
        return self.logger.warning("Skipping mount validation: %s" % colorize(mount_name, "yellow", bold=True))

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
                        raise ValueError(
                            "Please use the root_subvol parameter instead of setting the option manually in the root mount."
                        )
                    elif mount_config["type"] not in ["btrfs", "bcachefs"]:
                        raise ValueError("subvol option can only be used with btrfs or bcachefs mounts.")
        elif parameter not in MOUNT_PARAMETERS:
            raise ValueError("Invalid parameter in mount: %s" % parameter)


def _merge_mounts(self, mount_name: str, mount_config, mount_class) -> None:
    """Merges the passed mount config with the existing mount."""
    if mount_name not in self[mount_class]:
        self.logger.debug("[%s] Skipping mount merge, mount not found: %s" % (mount_class, mount_name))
        return mount_config

    self.logger.info("[%s] Updating mount: %s" % (mount_class, mount_name))
    self.logger.debug("[%s] Updating mount with: %s" % (mount_name, mount_config))
    if "options" in self[mount_class][mount_name] and "options" in mount_config:
        self.logger.debug("Merging options: %s" % mount_config["options"])
        self[mount_class][mount_name]["options"] = self[mount_class][mount_name]["options"] | set(
            mount_config["options"]
        )
        mount_config.pop("options")

    return dict(self[mount_class][mount_name], **mount_config)


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
        if mount_type in ["vfat", "ext4", "xfs"]:
            self["kmod_init"] = mount_type
        elif mount_type == "nilfs2":
            self["binaries"] = "mount.nilfs2"
        elif mount_type == "btrfs":
            if "ugrd.fs.btrfs" not in self["modules"]:
                self.logger.info("Auto-enabling module: %s", colorize("btrfs", "cyan"))
                self["modules"] = "ugrd.fs.btrfs"
        elif mount_type == "bcachefs":
            if "ugrd.fs.bcachefs" not in self["modules"]:
                self.logger.info("Auto-enabling module: %s", colorize("bcachefs", "cyan"))
                self["modules"] = "ugrd.fs.bcachefs"
        elif mount_type not in ["proc", "sysfs", "devtmpfs", "squashfs", "tmpfs", "devpts"]:
            self.logger.warning("Unknown mount type: %s" % colorize(mount_type, "red", bold=True))

    self[mount_class][mount_name] = mount_config
    self.logger.debug("[%s] Added mount: %s" % (mount_name, mount_config))

    if mount_class == "mounts":
        # Define the mountpoint path for standard mounts
        self["paths"] = mount_config["destination"]


def _process_mounts_multi(self, mount_name: str, mount_config) -> None:
    _process_mount(self, mount_name, mount_config)


def _process_late_mounts_multi(self, mount_name: str, mount_config) -> None:
    _process_mount(self, mount_name, mount_config, "late_mounts")


def _get_mount_source_type(self, mount: dict, with_val=False) -> str:
    """Gets the source from the mount config."""
    for source_type in SOURCE_TYPES:
        if source_type in mount:
            if with_val:
                return source_type, mount[source_type]
            return source_type
    raise ValueError("No source type found in mount: %s" % mount)


def _get_mount_str(self, mount: dict, pad=False, pad_size=44) -> str:
    """returns the mount source string based on the config,
    the output string should work with fstab and mount commands.
    pad: pads the output string with spaces, defined by pad_size (44)."""
    mount_type, mount_name = _get_mount_source_type(self, mount, with_val=True)
    out_str = mount_name if mount_type == "path" else f"{mount_type.upper()}={mount_name}"

    if pad:
        if len(out_str) > pad_size:
            pad_size = len(out_str) + 1
        out_str = out_str.ljust(pad_size, " ")

    return out_str


def _to_mount_cmd(self, mount: dict) -> str:
    """Prints the object as a mount command."""
    out = [f"if ! grep -qs {mount['destination']} /proc/mounts; then"]

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
    """Generates the fstab from the specified mounts."""
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


@contains("hostonly", "Skipping mount autodetection, hostonly mode is disabled.", log_level=30)
def get_mounts_info(self) -> None:
    """Gets the mount info for all devices."""
    with open("/proc/mounts", "r") as mounts:
        for line in mounts:
            device, mountpoint, fstype, options, _, _ = line.split()
            self["_mounts"][mountpoint] = {"device": device, "fstype": fstype, "options": options.split(",")}


@contains("hostonly", "Skipping blkid enumeration, hostonly mode is disabled.", log_level=30)
def get_blkid_info(self, device=None) -> dict:
    """Gets the blkid info for all devices if no device is passed.
    Gets the blkid info for the passed device if a device is passed.
    The info is stored in self['_blkid_info']."""
    from re import search

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
        dev, info = device_info.split(": ")
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


@contains("init_target", "init_target must be set", raise_exception=True)
@contains(
    "autodetect_init_mount", "Skipping init mount autodetection, autodetect_init_mount is disabled.", log_level=30
)
@contains("hostonly", "Skipping init mount autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_init_mount(self, parent=None) -> None:
    """Checks the parent directories of init_target, if the path is a mountpoint, add it to late_mounts."""
    if not parent:
        parent = self["init_target"].parent
    if parent == Path("/"):
        return
    if str(parent) in self["_mounts"]:
        self.logger.info("Detected init mount: %s" % colorize(parent, "cyan"))
        mount_name = str(parent).removeprefix("/")
        mount_dest = str(parent)
        mount_device = self["_mounts"][str(parent)]["device"]
        mount_type = self["_mounts"][str(parent)]["fstype"]
        mount_options = self["_mounts"][str(parent)]["options"]
        blkid_info = self["_blkid_info"][mount_device]
        mount_source_type, mount_source = _get_mount_source_type(self, blkid_info, with_val=True)
        self["late_mounts"][mount_name] = {
            "destination": mount_dest,
            mount_source_type: mount_source,
            "type": mount_type,
            "options": mount_options,
        }
    autodetect_init_mount(self, parent.parent)


@contains("hostonly", "Skipping virtual block device enumeration, hostonly mode is disabled.", log_level=30)
def get_virtual_block_info(self) -> dict:
    """Populates the virtual block device info. (previously device mapper only)
    Disables device mapper autodetection if no virtual block devices are found.
    """
    if self.get("_vblk_info"):
        self.logger.debug("Virtual device info already set.")
        return

    if not Path("/sys/devices/virtual/block").exists():
        self["autodetect_root_dm"] = False
        self.logger.warning("No virtual block devices found, disabling device mapper autodetection.")
        return

    for virt_device in Path("/sys/devices/virtual/block").iterdir():
        if virt_device.name.startswith("dm-") or virt_device.name.startswith("md"):
            maj, minor = (virt_device / "dev").read_text().strip().split(":")
            self["_vblk_info"][virt_device.name] = {
                "major": maj,
                "minor": minor,
                "holders": [holder.name for holder in (virt_device / "holders").iterdir()],
                "slaves": [slave.name for slave in (virt_device / "slaves").iterdir()],
            }
            if (virt_device / "dm").exists():
                self["_vblk_info"][virt_device.name]["uuid"] = (virt_device / "dm/uuid").read_text().strip()
            elif (virt_device / "md").exists():
                self["_vblk_info"][virt_device.name]["uuid"] = (virt_device / "md/uuid").read_text().strip()
                self["_vblk_info"][virt_device.name]["level"] = (virt_device / "md/level").read_text().strip()
            else:
                raise AutodetectError("Failed to get virtual device name: %s" % virt_device.name)

            try:
                self["_vblk_info"][virt_device.name]["name"] = (virt_device / "dm/name").read_text().strip()
            except FileNotFoundError:
                self.logger.warning(
                    "No device mapper name found for: %s" % colorize(virt_device.name, "red", bold=True)
                )
                self["_vblk_info"][virt_device.name]["name"] = virt_device.name  # we can pretend

    if self["_vblk_info"]:
        self.logger.info("Found virtual block devices: %s" % colorize(", ".join(self["_vblk_info"].keys()), "cyan"))
        self.logger.debug("Virtual block device info: %s" % pretty_print(self["_vblk_info"]))
    else:
        self.logger.debug("No virtual block devices found.")


def _get_device_id(device: str) -> str:
    """Gets the device id from the device path."""
    return Path(device).stat().st_rdev >> 8, Path(device).stat().st_rdev & 0xFF


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

    self.logger.info("[%s] Detected virtual block device: %s" % (mountpoint, colorize(source_device, "cyan")))
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

    try:
        blkid_info = self["_blkid_info"][f"/dev/{slave_source}"]
    except KeyError:
        if slave_source in self["_vblk_info"]:
            blkid_info = self["_blkid_info"][f"/dev/mapper/{self['_vblk_info'][slave_source]['name']}"]
        else:
            raise AutodetectError("Unable to find blkid info for device mapper slave: %s" % slave_source)
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

    autodetect_mount_kmods(self, slave_source)

    for slave in self["_vblk_info"][dev_name]["slaves"]:
        try:
            _autodetect_dm(self, mountpoint, slave)  # Just pass the slave device name, as it will be re-detected
            self.logger.info(
                "[%s] Autodetected device mapper container: %s" % (source_device.name, colorize(slave, "cyan"))
            )
        except KeyError:
            self.logger.debug("Slave does not appear to be a DM device: %s" % slave)


@contains("autodetect_root_raid", "Skipping RAID autodetection, autodetect_root_raid is disabled.", log_level=30)
@contains("hostonly", "Skipping RAID autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_raid(self, mount_loc, dm_name, blkid_info) -> None:
    """Autodetects MD RAID mounts and sets the raid config.
    Adds kmods for the raid level to the autodetect list.
    """
    if "ugrd.fs.mdraid" not in self["modules"]:
        self.logger.info("Autodetected MDRAID mount, enabling the %s module." % colorize("mdraid", "cyan"))
        self["modules"] = "ugrd.fs.mdraid"

    if level := self["_vblk_info"][dm_name].get("level"):
        self.logger.info("[%s] MDRAID level: %s" % (mount_loc.name, colorize(level, "cyan")))
        self["_kmod_auto"] = level
    else:
        raise AutodetectError("[%s] Failed to autodetect MDRAID level: %s" % (dm_name, blkid_info))


@contains("autodetect_root_lvm", "Skipping LVM autodetection, autodetect_root_lvm is disabled.", log_level=20)
@contains("hostonly", "Skipping LVM autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_lvm(self, mount_loc, dm_num, blkid_info) -> None:
    """Autodetects LVM mounts and sets the lvm config."""
    if "ugrd.fs.lvm" not in self["modules"]:
        self.logger.info("Autodetected LVM mount, enabling the %s module." % colorize("lvm", "cyan"))
        self["modules"] = "ugrd.fs.lvm"

    if uuid := blkid_info.get("uuid"):
        self.logger.info("[%s] LVM volume contianer uuid: %s" % (mount_loc.name, colorize(uuid, "cyan")))
        self["lvm"] = {self["_vblk_info"][dm_num]["name"]: {"uuid": uuid}}
    else:
        raise AutodetectError("Failed to autodetect LVM volume uuid: %s" % mount_loc.name)


@contains("autodetect_root_luks", "Skipping LUKS autodetection, autodetect_root_luks is disabled.", log_level=30)
@contains("hostonly", "Skipping LUKS autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_luks(self, mount_loc, dm_num, blkid_info) -> None:
    """Autodetects LUKS mounts and sets the cryptsetup config."""
    if "ugrd.crypto.cryptsetup" not in self["modules"]:
        self.logger.info(
            "Autodetected LUKS mount, enabling the cryptsetup module: %s" % colorize(mount_loc.name, "cyan")
        )
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
        self.logger.error("Device mapper slaves: %s" % colorize(self["_vblk_info"][dm_num]["slaves"], "red", bold=True))
        raise AutodetectError("Multiple slaves found for device mapper device, unknown type: %s" % mount_loc.name)

    dm_type = blkid_info.get("type")
    if dm_type != "crypto_LUKS":
        if not blkid_info.get("uuid"):  # No uuid will be defined if there are detached headers
            if not self["cryptsetup"][mount_loc.name].get("header_file"):
                raise AutodetectError("[%s] Unknown LUKS mount type: %s" % (mount_loc.name, dm_type))
        else:  # If there is some uuid and it's not LUKS, that's a problem
            raise AutodetectError(
                "[%s] Unknown device mapper slave type: %s" % (self["_vblk_info"][dm_num]["slaves"][0], dm_type)
            )

    # Configure cryptsetup based on the LUKS mount
    if uuid := blkid_info.get("uuid"):
        self.logger.info("[%s] LUKS volume uuid: %s" % (mount_loc.name, colorize(uuid, "cyan")))
        self["cryptsetup"] = {self["_vblk_info"][dm_num]["name"]: {"uuid": uuid}}
    elif partuuid := blkid_info.get("partuuid"):
        self.logger.info("[%s] LUKS volume partuuid: %s" % (mount_loc.name, colorize(partuuid, "cyan")))
        self["cryptsetup"] = {self["_vblk_info"][dm_num]["name"]: {"partuuid": partuuid}}

    self.logger.info(
        "[%s] Configuring cryptsetup for LUKS mount (%s) on: %s\n%s"
        % (mount_loc.name, self["_vblk_info"][dm_num]["name"], dm_num, pretty_print(self["cryptsetup"]))
    )


def _resolve_dev(self, device_path) -> str:
    """Resolves a device path, if possible.
    Useful for cases where the device in blkid differs from the device in /proc/mounts.
    """
    major, minor = _get_device_id(self["_mounts"][device_path]["device"])
    for device in self["_blkid_info"]:
        check_major, check_minor = _get_device_id(device)
        if (major, minor) == (check_major, check_minor):
            self.logger.info(
                "Resolved device: %s -> %s" % (self["_mounts"][device_path]["device"], colorize(device, "cyan"))
            )
            return device
    self.logger.warning("Failed to resolve device: %s" % colorize(self["_mounts"]["/"]["device"], "red", bold=True))
    return self["_mounts"][device_path]["device"]


def _resolve_overlay_lower_dir(self, mountpoint) -> str:
    for option in self["_mounts"][mountpoint]["options"]:
        if option.startswith("lowerdir="):
            return option.removeprefix("lowerdir=")
    raise AutodetectError(
        "[%s] No lower overlayfs mountpoint found: %s" % mountpoint, self["_mounts"][mountpoint]["options"]
    )


def _resolve_overlay_lower_device(self, mountpoint) -> dict:
    """Returns device for the lower overlayfs mountpoint."""
    if self["_mounts"][mountpoint]["fstype"] != "overlay":
        return self["_mounts"][mountpoint]["device"]

    lowerdir = _resolve_overlay_lower_dir(self, mountpoint)
    return self["_mounts"][lowerdir]["device"]


@contains("autodetect_root", "Skipping root autodetection, autodetect_root is disabled.", log_level=30)
@contains("hostonly", "Skipping root autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_root(self) -> None:
    """Sets self['mounts']['root']'s source based on the host mount."""
    if "/" not in self["_mounts"]:
        self.logger.error("Host mounts: %s" % pretty_print(self["_mounts"]))
        raise AutodetectError(
            "Root mount not found in host mounts.\nCurrent mounts: %s" % pretty_print(self["_mounts"])
        )
    # Sometimes the root device listed in '/proc/mounts' differs from the blkid info
    root_dev = self["_mounts"]["/"]["device"]
    if self["resolve_root_dev"]:  # Sometimes the root device listed in '/proc/mounts' differs from the blkid info
        root_dev = _resolve_dev(self, "/")
    if ":" in root_dev:  # only use the first device
        root_dev = root_dev.split(":")[0]
        for alt_devices in root_dev.split(":")[1:]:  # But ensure kmods are loaded for all devices
            autodetect_mount_kmods(self, alt_devices)
    _autodetect_mount(self, "/")
    if self["autodetect_root_dm"]:
        _autodetect_dm(self, "/")


def _autodetect_mount(self, mountpoint) -> None:
    """Sets mount config for the specified mountpoint."""
    if mountpoint not in self["_mounts"]:
        self.logger.error("Host mounts: %s" % pretty_print(self["_mounts"]))
        raise AutodetectError("auto_mount mountpoint not found in host mounts: %s" % mountpoint)

    mount_device = _resolve_overlay_lower_device(self, mountpoint)

    if ":" in mount_device:  # Handle bcachefs
        mount_device = mount_device.split(":")[0]

    if mount_device not in self["_blkid_info"]:
        get_blkid_info(self, mount_device)

    mount_info = self["_blkid_info"][mount_device]
    autodetect_mount_kmods(self, mount_device)
    mount_name = "root" if mountpoint == "/" else mountpoint.removeprefix("/")
    if mount_name in self["mounts"] and any(s_type in self["mounts"][mount_name] for s_type in SOURCE_TYPES):
        return self.logger.warning(
            "[%s] Skipping autodetection, mount config already set:\n%s"
            % (colorize(mountpoint, "yellow"), pretty_print(self["mounts"][mount_name]))
        )

    mount_config = {mount_name: {"type": "auto", "options": ["ro"]}}  # Default to auto and ro
    if mount_type := mount_info.get("type"):
        self.logger.info("Autodetected mount type: %s" % colorize(mount_type, "cyan"))
        mount_config[mount_name]["type"] = mount_type.lower()

    for source_type in SOURCE_TYPES:
        if source := mount_info.get(source_type):
            self.logger.info(
                "[%s] Autodetected mount source: %s=%s"
                % (mount_name, colorize(source_type, "blue"), colorize(source, "cyan"))
            )
            mount_config[mount_name][source_type] = source
            break
    else:
        raise AutodetectError("[%s] Failed to autodetect mount source." % mountpoint)

    self["mounts"] = mount_config


@contains("auto_mounts", "Skipping auto mounts, auto_mounts is empty.", log_level=10)
@contains("hostonly", "Skipping mount autodetection, hostonly mode is disabled.", log_level=30)
def autodetect_mounts(self) -> None:
    """Configured the mount config for a device based on the host mount config."""
    for mountpoint in self["auto_mounts"]:
        _autodetect_mount(self, mountpoint)


def mount_base(self) -> list[str]:
    """Generates mount commands for the base mounts.
    Must be run before variables are used, as it creates the /run/vars directory.
    """
    out = []
    for mount in self["mounts"].values():
        if mount.get("base_mount"):
            out += _to_mount_cmd(self, mount)
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
    Keeps re-attempting with mount_timeout or rootdelay until successful.
    mount_retries sets the number of times to retry the mount, infinite otherwise.
    """
    out = [
        'einfo "Attempting to mount all filesystems."',
        f"timeout=$(readvar rootdelay {self.get('mount_timeout', 1)})",
    ]

    if retries := self.get("mount_retries"):
        out += [
            f'retry {retries} "$timeout" mount -a || rd_fail "Failed to mount all filesystems."',
        ]
    else:
        out += [
            "while ! mount -a; do",  # Actually retry forever, retry with a short timeout may fail
            '    if prompt_user "Press enter to break, waiting: ${timeout}s" "$timeout"; then',
            '        rd_fail "Failed to mount all filesystems."',
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

    mount_type, mount_val = _get_mount_source_type(self, mount, with_val=True)
    # If a destination path is passed, like for /, use that instead of the mount's destination
    destination_path = str(mount["destination"]) if destination_path is None else destination_path

    # Using the mount path, get relevant host mount info
    host_source_dev = _resolve_overlay_lower_device(self, destination_path)
    if ":" in host_source_dev:  # Handle bcachefs
        host_source_dev = host_source_dev.split(":")[0]
    if destination_path == "/" and self["resolve_root_dev"]:
        host_source_dev = _resolve_dev(self, "/")

    host_mount_options = self["_mounts"][destination_path]["options"]
    for option in mount.get("options", []):
        if mount.get("no_validate_options"):
            break  # Skip host option validation if this is set
        if option == "ro":  # Allow the ro option to be set in the config
            continue
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


def mount_root(self) -> list[str]:
    """Mounts the root partition to $MOUNTS_ROOT_TARGET."""
    return [
        'if grep -qs "$(readvar MOUNTS_ROOT_TARGET)" /proc/mounts; then',
        '    ewarn "Root mount already exists, unmounting: $(readvar MOUNTS_ROOT_TARGET)"',
        '    umount "$(readvar MOUNTS_ROOT_TARGET)"',
        "fi",
        '''einfo "Mounting '$(readvar MOUNTS_ROOT_SOURCE)' ($(readvar MOUNTS_ROOT_TYPE)) to '$(readvar MOUNTS_ROOT_TARGET)' with options: $(readvar MOUNTS_ROOT_OPTIONS)"''',
        f'retry {self["mount_retries"] or -1} {self["mount_timeout"]} mount "$(readvar MOUNTS_ROOT_SOURCE)" -t "$(readvar MOUNTS_ROOT_TYPE)" "$(readvar MOUNTS_ROOT_TARGET)" -o "$(readvar MOUNTS_ROOT_OPTIONS)"',
    ]


def export_mount_info(self) -> None:
    """Exports mount info based on the config to /run/MOUNTS_ROOT_{option}"""
    self["exports"]["MOUNTS_ROOT_SOURCE"] = _get_mount_str(self, self["mounts"]["root"])
    self["exports"]["MOUNTS_ROOT_TYPE"] = self["mounts"]["root"].get("type", "auto")
    self["exports"]["MOUNTS_ROOT_OPTIONS"] = ",".join(self["mounts"]["root"]["options"])
    self["exports"]["MOUNTS_ROOT_TARGET"] = self["mounts"]["root"]["destination"]


def autodetect_mount_kmods(self, device) -> None:
    """Autodetects the kernel modules for a block device."""
    if device_kmods := resolve_blkdev_kmod(self, device):
        self.logger.info("Auto-enabling kernel modules for device: %s" % colorize(", ".join(device_kmods), "cyan"))
        self["_kmod_auto"] = device_kmods


def resolve_blkdev_kmod(self, device) -> list[str]:
    """Gets the kmod name for a block device."""
    dev = Path(device)
    while dev.is_symlink():
        dev = dev.resolve()
    device_name = dev.name
    if device_name.startswith("dm-") or dev.parent.name == "mapper" or dev.parent.name.startswith("vg"):
        return ["dm_mod"]
    elif device_name.startswith("nvme"):
        return ["nvme"]
    elif device_name.startswith("vd"):
        return ["virtio_blk"]
    elif device_name.startswith("sd"):
        return ["sd_mod"]
    elif device_name.startswith("mmcblk"):
        return ["mmc_block"]
    elif device_name.startswith("sr"):
        return ["sr_mod"]
    elif device_name.startswith("md"):
        return ["md_mod"]
    else:
        self.logger.error(
            "[%s] Unable to determine kernel module for block device: %s"
            % (device_name, colorize(device, "red", bold=True))
        )
        return []
