__author__ = "desultory"
__version__ = "4.2.2"

from pathlib import Path
from platform import uname
from re import search
from struct import error as StructError
from struct import unpack
from subprocess import run

from ugrd.exceptions import AutodetectError, ValidationError
from ugrd.kmod import BuiltinModuleError, DependencyResolutionError, IgnoredModuleError, MissingModuleError
from zenlib.util import colorize as c_
from zenlib.util import contains, unset

_KMOD_ALIASES: dict[str, str] = {}
MODULE_METADATA_FILES = ["modules.order", "modules.builtin", "modules.builtin.modinfo"]


def _normalize_kmod_name(self, module: str) -> str:
    """Replaces -'s with _'s in a kernel module name.
    ignores modules defined in kmod_no_normalize.
    """
    if module in self.get("kmod_no_normalize", []):
        self.logger.debug(f"Not normalizing kernel module name: {module}")
        return module
    return module.replace("-", "_")


def _normalize_kmod_alias(self, alias: str) -> str:
    """Gets the base alias name from kmod alias info
    gets data after : and , if present.
    """
    if not alias:
        return ""
    alias = alias.split(":", 1)[-1]  # Strip bus type
    alias = alias.split(",", 1)[-1]
    return _normalize_kmod_name(self, alias)


def _resolve_kmod_alias(self, module: str) -> str:
    """Attempts to resolve a kernel module alias to a module name.
    Uses  /lib/modules/<kernel_version>/modules.alias to find the module name.
    normalizes - to _ then replaces _ with [_-] to allow for both _ and - in the module name.
    """
    module = module.replace("-", "_")
    module = module.replace("_", "[_-]")  # Allow for both _ and - in the module name
    for alias, kmod in _KMOD_ALIASES.items():
        if search(module, alias):
            self.logger.info(f"Resolved kernel module alias: {c_(alias, 'blue')} -> {c_(kmod, 'cyan')}")
            return kmod

    raise MissingModuleError(f"Failed to resolve kernel module alias: {module}")


def _process_kernel_modules_multi(self, module: str) -> None:
    """Adds kernel modules to self['kernel_modules']."""
    module = _normalize_kmod_name(self, module)
    if module in self["kmod_ignore"]:
        self.logger.debug("[%s] Module is in the ignore list." % module)
        self["_kmod_removed"] = module
        return

    self.logger.debug("Adding kernel module to kernel_modules: %s", module)
    self["kernel_modules"].append(module)


def _process_kmod_init_multi(self, module: str) -> None:
    """Adds init modules to self['kernel_modules']."""
    module = _normalize_kmod_name(self, module)
    if module in self["kmod_ignore"]:
        raise IgnoredModuleError("kmod_init module is in the ignore list: %s" % module)
    self["kmod_init"].append(module)
    self.logger.debug("Adding kmod_init module to kernel_modules: %s", module)
    self["kernel_modules"] = module


def _process_kmod_init_optional_multi(self, module: str) -> None:
    """Adds an optional kmod init module"""
    module = _normalize_kmod_name(self, module)
    if module in self["kmod_ignore"]:
        self.logger.warning(f"Optional kmod_init module is in the ignore list: {c_(module, 'yellow', bold=True)}")
        self["_kmod_removed"] = module
        return
    if module in self["kmod_init"]:
        self.logger.debug(f"Optional kmod_init module is already in kmod_init: {c_(module, 'yellow', bold=True)}")
        return
    self.logger.debug(f"Adding optional kmod_init module: {c_(module, 'magenta')}")
    self["kmod_init_optional"].append(module)


def _process__kmod_auto_multi(self, module: str) -> None:
    """Adds autodetected modules to self['kernel_modules']."""
    module = _normalize_kmod_name(self, module)
    if module in self["kmod_ignore"]:
        self.logger.debug("Autodetected module is in the ignore list: %s" % module)
        self["_kmod_removed"] = module
        return
    self.logger.debug("Adding autodetected kernel module to kernel_modules: %s", module)
    self["_kmod_auto"].append(module)


def _get_kmod_info(self, module: str) -> tuple[str, dict]:
    """
    Runs modinfo on a kernel module, parses the output and stored the results in self['_kmod_modinfo'].
    !!! Should be run after metadata is processed so the kver is set properly !!!

    Returns the module info as a dictionary with the following keys:
    - filename: The path to the module file.
    - depends: A list of module dependencies.
    - softdep: A list of soft dependencies.
    - firmware: A list of firmware files required by the module.
    Raises:
        DependencyResolutionError: If the modinfo command fails, returns no output, or the module name can't be resolved.
    """
    module = _normalize_kmod_name(self, module)
    if module in self["_kmod_modinfo"]:
        return module, self["_kmod_modinfo"][module]
    args = ["modinfo", module, "--set-version", self["kernel_version"]]

    try:
        self.logger.debug("[%s] Modinfo command: %s" % (module, " ".join(args)))
        cmd = run(args, capture_output=True)
    except RuntimeError as e:
        raise DependencyResolutionError("[%s] Failed to run modinfo command: %s" % (module, " ".join(args))) from e

    if not cmd.stdout and cmd.stderr:
        try:
            resolved_module = _resolve_kmod_alias(self, module)
            return _get_kmod_info(self, resolved_module)
        except MissingModuleError:
            raise DependencyResolutionError(
                "[%s] Modinfo returned no output and the alias name could no be resolved." % module
            )

    module_info: dict[str, list[str] | str] = {"filename": "", "depends": [], "softdep": [], "firmware": []}
    for line in cmd.stdout.decode().split("\n"):
        line = line.strip()
        if line.startswith("filename:"):
            module_info["filename"] = line.split()[1]
        elif line.startswith("depends:") and line != "depends:":
            if "," in line:
                kmod_deps = line.split(":")[1].lstrip().split(",")
                module_info["depends"] = [_normalize_kmod_name(self, dep) for dep in kmod_deps]
            else:
                module_info["depends"] = [_normalize_kmod_name(self, line.split()[1])]
        elif line.startswith("softdep:"):
            softdep_info = line.rsplit(":", 1)[1].strip()
            if "," in softdep_info:
                kmod_deps = softdep_info.split(",")
                module_info["softdep"] = [_normalize_kmod_name(self, dep) for dep in kmod_deps]
            else:
                module_info["softdep"] = [_normalize_kmod_name(self, softdep_info)]
        elif line.startswith("firmware:"):
            module_info["firmware"].extend(line.split()[1:])  # type: ignore[union-attr]  # ignore for now, fixup later

    if not module_info.get("filename"):
        raise DependencyResolutionError("[%s] Failed to process modinfo output: %s" % (module, cmd.stdout.decode()))

    self.logger.debug("[%s] Module info: %s" % (module, module_info))
    self["_kmod_modinfo"][module] = module_info
    return module, module_info


@unset("no_kmod", "no_kmod is enabled, skipping module alias enumeration.", log_level=30)
def get_module_aliases(self):
    """Processes the kernel module aliases from /lib/modules/<kernel_version>/modules.alias."""
    alias_file = Path("/lib/modules") / self["kernel_version"] / "modules.alias"
    if not alias_file.exists():
        self.logger.error(f"Kernel module alias file does not exist: {c_(alias_file, 'red', bold=True)}")
    else:
        for line in alias_file.read_text().splitlines():
            _, alias, module = line.strip().split(" ", 2)
            _KMOD_ALIASES[_normalize_kmod_alias(self, alias)] = _normalize_kmod_name(self, module)


@unset("no_kmod", "no_kmod is enabled, skipping builtin module enumeration.", log_level=30)
def get_builtin_module_info(self) -> None:
    """Gets the kernel module aliases from /lib/modules/<kernel_version>/modules.builtin.modinfo.
    puts it in _kmod_modinfo.
    also populates the _KMOD_ALIASES global variable with the aliases.
    """

    builtin_modinfo_file = Path("/lib/modules") / self["kernel_version"] / "modules.builtin.modinfo"
    if not builtin_modinfo_file.exists():
        self.logger.error(f"Builtin modinfo file does not exist: {c_(builtin_modinfo_file, 'red', bold=True)}")
    else:
        for line in builtin_modinfo_file.read_bytes().split(b"\x00"):
            """ Lines are in the format <name>.<parameter>=<value>"""
            line = line.decode("utf-8", errors="ignore").strip()
            if not line or "." not in line or "=" not in line:
                continue
            name, parameter = line.split(".", 1)
            name = _normalize_kmod_name(self, name)
            parameter, value = parameter.split("=", 1)
            modinfo = self["_kmod_modinfo"].get(
                name, {"filename": "(builtin)", "depends": [], "softdep": [], "firmware": []}
            )
            if parameter == "firmware":
                modinfo["firmware"].append(value)
            elif parameter != "alias":
                continue

            alias = _normalize_kmod_alias(self, value)
            self["_kmod_modinfo"][name] = modinfo
            _KMOD_ALIASES[alias] = name  # Store the alias in the global aliases dict


@contains("kmod_autodetect_lspci", "kmod_autodetect_lspci is not enabled, skipping.")
def _autodetect_modules_lspci(self) -> None:
    """Uses /sys/bus/pci/drivers to get a list of all kernel modules.
    Similar to lspci -k."""
    lspci_kmods = set()
    for driver in Path("/sys/bus/pci/drivers").iterdir():
        if not driver.is_dir():
            self.logger.debug("Skipping non-directory: %s" % driver)
            continue
        module = driver / "module"
        if not module.exists():
            self.logger.debug("Skipping driver without module: %s" % driver)
            continue
        lspci_kmods.add(module.resolve().name)
        self.logger.debug("[%s] Autodetected kernel module: %s" % (driver, module.resolve().name))

    self["_kmod_auto"] = list(lspci_kmods)


@contains("kmod_autodetect_lsmod", "kmod_autodetect_lsmod is not enabled, skipping.")
def _autodetect_modules_lsmod(self) -> None:
    """Gets the name of all currently used kernel modules."""
    if self.get("kernel_version") and self["kernel_version"] != uname().release:
        self.logger.warning(
            "Kernel version is set to %s, but the current kernel version is %s"
            % (self["kernel_version"], uname().release)
        )

    with open("/proc/modules", "r") as f:
        modules = [line.split()[0] for line in f.readlines()]

    if len(modules) > 25:
        self.logger.warning(
            f"[{len(modules)}] More than 25 kernel modules were autodetected from the running kernel. If lsmod detection is required for your use case, please file a bug report so more appropriate detection methods can be implemented."
        )
    for module in modules:
        self["_kmod_auto"] = module.split()[0]


@unset("no_kmod", "no_kmod is enabled, skipping module detection.", log_level=30)
@contains("hostonly", "Skipping kmod autodetection, hostonly is disabled.", log_level=30)
def autodetect_modules(self) -> None:
    """Autodetects kernel modules from lsmod and/or lspci -k."""
    if not self["kmod_autodetect_lsmod"] and not self["kmod_autodetect_lspci"]:
        self.logger.debug("No autodetection methods are enabled.")
        return
    _autodetect_modules_lsmod(self)
    _autodetect_modules_lspci(self)
    if self["_kmod_auto"]:
        self.logger.info("Autodetected kernel modules: %s" % c_(", ".join(self["_kmod_auto"]), "cyan"))
    else:
        self.logger.warning("No kernel modules were autodetected.")


def _find_kernel_image(self) -> Path:
    """Finds the kernel image,
    Searches /boot, then /efi for prefixes 'vmlinuz', 'linux', and 'bzImage'.
    Searches for the file with the prefix, then files starting with the prefix and a hyphen.
    If multiple files are found, uses the last modified."""

    def search_prefix(prefix: str) -> Path | None:
        for path in ["/boot", "/efi"]:
            kernel_path: Path = (Path(path) / f"{prefix}").resolve()
            if kernel_path.exists():
                return kernel_path
            kernel_path = Path()  # Reset because the supplied prefix file doesn't exit
            for file in Path(path).glob(f"{prefix}-*"):
                file = file.resolve()
                if not file.is_file():
                    continue  # Skip directories and non-files
                if str(kernel_path) == ".":  # If kernel_path is not set, set it to the first file found with the prefix
                    kernel_path = file
                elif file.stat().st_mtime > kernel_path.stat().st_mtime:
                    # if the file is newer than the current kernel_path, set it as the new kernel_path
                    kernel_path = file
            if str(kernel_path) != ".":
                # If a file with the prefix was found, return it
                return kernel_path
        return self.logger.debug("Failed to find kernel image with prefix: %s" % prefix)

    for prefix in ["vmlinuz", "linux", "bzImage"]:
        if kernel_path := search_prefix(prefix):
            self.logger.info(f"Detected kernel image: {c_(str(kernel_path), 'cyan')}")
            return kernel_path
    raise AutodetectError("Failed to find kernel image")


def _get_kver_from_header(self) -> str:
    """Tries to read the kernel version from the kernel header.
    The offset of the kernel version is stored in 2 bytes at 0x020E.
    An additional sector is skipped, so the offset is increased by 512.
    The version string can be up to 127 bytes long and is null-terminated.
    https://www.kernel.org/doc/html/v6.7/arch/x86/boot.html#the-real-mode-kernel-header
    """
    kernel_path = _find_kernel_image(self)
    try:
        kver_offset = unpack("<h", kernel_path.read_bytes()[0x020E:0x0210])[0] + 512
    except StructError as e:
        raise AutodetectError(f"Failed to read kernel version offset from: {kernel_path}") from e

    header = kernel_path.read_bytes()[kver_offset : kver_offset + 127]
    # Cut at the first null byte, decode to utf-8, and split at the first space
    kver = header[: header.index(0)].decode("utf-8").split()[0]
    return kver


def _process_kernel_version(self, kver: str) -> None:
    """Sets the kerenl_version, checks that the kmod directory exits, sets the _kmod_dir variable.
    If no_kmod is set, logs a warning because no_kmod will skip kmod functions later.

    If the kmod directory does not exist, and no_kmod is not set, raises a ValidationError.
    If there is no /lib/modules directory, assumes 'no_kmod' is true and logs a critical error.
    """
    if self["no_kmod"]:
        # Log a warning is no_kmod is already set, but a kver is passed. Check it anyways
        self.logger.warning("kernel_version is set, but no_kmod is enabled.")

    # Checks that the kmod directoty exists for the kernel version
    kmod_dir = Path("/lib/modules") / kver
    if not kmod_dir.exists():
        # If no_kmod is set, log a warning and continue
        if self["no_kmod"]:
            return self.logger.warning(
                "[%s] Kernel module directory does not exist, but no_kmod is set, continuing." % kver
            )
        elif not Path(
            "/lib/modules"
        ).exists():  # If /lib/modules doesn't exist, assume no_kmod is true because no kmods are installed
            self.logger.critical(f"/lib/modules directory does not exist, assuming {c_('no_kmod', 'blue')}=true.")
            self["no_kmod"] = True
            return

        # If there are other kernel versions available, log them for the user
        self.logger.error(f"Available kernel versions: {', '.join([d.name for d in Path('/lib/modules').iterdir()])}")
        self.logger.info(
            "If kernel modules are not installed, and not required, set `no_kmod = true` to skip this check."
        )
        raise ValidationError(f"Kernel module directory does not exist for kernel: {kver}")

    self.data["kernel_version"] = kver
    self.data["_kmod_dir"] = kmod_dir


def _handle_arch_kernel(self) -> None:
    """Checks that an arch package owns the kernel version directory."""
    kernel_path = Path("/lib/modules") / self["kernel_version"] / "vmlinuz"
    try:
        cmd = self._run(["pacman", "-Qqo", kernel_path])
        if not self["out_file"]:
            self["out_file"] = f"{kernel_path.resolve().parent}/initramfs-{cmd.stdout.decode().strip()}.img"
            self.logger.info("Setting out_file to: %s" % c_(self["out_file"], "green", bold=True))
    except RuntimeError as e:
        raise DependencyResolutionError("Failed to check ownership of kernel module directory") from e


@unset("kernel_version", "Kernel version is already set, skipping.", log_level=30)
@unset("no_kmod", "no_kmod is enabled, skipping.", log_level=30)
def get_kernel_version(self) -> None:
    """Gets the kernel version using  uname -r.
    On arch systems, uses the kernel version from the kernel image.
    If the kmod directory doesnt't exit, attempts to find the kernel version from the kernel image."""
    try:
        cmd = self._run(["uname", "-r"])
    except RuntimeError as e:
        raise DependencyResolutionError("Failed to get running kernel version") from e

    try:
        self._run(["pacman", "-V"], fail_silent=True)
        self["kernel_version"] = _get_kver_from_header(self)
        _handle_arch_kernel(self)
    except FileNotFoundError:
        try:
            self["kernel_version"] = cmd.stdout.decode("utf-8").strip()
        except DependencyResolutionError:
            self["kernel_version"] = _get_kver_from_header(self)
    self.logger.info("Detected kernel version: %s" % c_(self["kernel_version"], "magenta", bold=True))


@contains("kmod_init", "kmod_init is empty, skipping.")
@unset("no_kmod", "no_kmod is enabled, skipping.", log_level=30)
def process_module_metadata(self) -> None:
    """Adds kernel module metadata files to dependencies."""
    for meta_file in MODULE_METADATA_FILES:
        meta_file_path = self["_kmod_dir"] / meta_file

        self.logger.debug(
            "[%s] Adding kernel module metadata files to dependencies: %s" % (self["kernel_version"], meta_file_path)
        )
        self["dependencies"] = meta_file_path


@contains("kmod_init", "kmod_init is empty, skipping.")
@unset("no_kmod", "no_kmod is enabled, skipping.", log_level=30)
def regen_kmod_metadata(self) -> None:
    """Regenerates kernel module metadata files using depmod."""
    self.logger.info("Regenerating kernel module metadata files.")
    build_dir = self._get_build_path("/")
    self._run(["depmod", "--basedir", build_dir, self["kernel_version"]])


def _add_kmod_firmware(self, kmod: str) -> None:
    """Adds firmware files for the specified kernel module to the initramfs.

    Attempts to run even if no_kmod is set; this will not work if there are no kmods/no kernel version set
    """
    try:
        kmod, modinfo = _get_kmod_info(self, kmod)
    except DependencyResolutionError as e:
        if self["no_kmod"]:
            return self.logger.warning(
                "[%s] Kernel module info for firmware detection does not exist, but no_kmod is set." % kmod
            )
        raise DependencyResolutionError("Kernel module info does not exist: %s" % kmod) from e

    if modinfo["firmware"] and not self["kmod_pull_firmware"]:
        # Log a warning if the kernel module has firmware files, but kmod_pull_firmware is not set
        self.logger.warning("[%s] Kernel module has firmware files, but kmod_pull_firmware is not set." % kmod)

    if not modinfo["firmware"] or not self.get("kmod_pull_firmware"):
        # No firmware files to add, or kmod_pull_firmware is not set
        return

    for firmware in modinfo["firmware"]:
        _add_firmware_dep(self, kmod, firmware)


def _add_firmware_dep(self, kmod: str, firmware: str) -> None:
    """Adds a kernel module firmware file to the initramfs dependencies."""
    kmod = _normalize_kmod_name(self, kmod)
    firmware_path = Path("/lib/firmware") / firmware
    if not firmware_path.exists():
        if firmware_path.with_suffix(firmware_path.suffix + ".xz").exists():
            firmware_path = firmware_path.with_suffix(firmware_path.suffix + ".xz")
            if self["kmod_decompress_firmware"]:  # otherise, just add it like a normal dependency
                self["xz_dependencies"] = firmware_path
                return self.logger.debug("[%s] Found xz compressed firmware file: %s" % (kmod, firmware_path))
        else:
            # Really, this should be a huge error, but with xhci_pci, it wants some renesas firmware that's not in linux-firmware and doesn't seem to matter
            return self.logger.error("[%s] Firmware file does not exist: %s" % (kmod, firmware_path))
    self.logger.debug("[%s] Adding firmware file to dependencies: %s" % (kmod, firmware_path))
    self["dependencies"] = firmware_path


def _process_kmod_dependencies(self, kmod: str, mod_tree=None) -> tuple[str, list[str]]:
    """Processes a kernel module's dependencies.

    If the kernel module is built in, only add firmware, don't resolve dependencies.

    Only add softdeps if kmod_ignore_softdeps is not set.

    Iterate over dependencies, adding them to kernel_mdules if they (or sub-dependencies) are not in the ignore list.
    If the dependency is already in the module tree, skip it to prevent infinite recursion.

    returns the name of the kernel module (in case it was an alias) and the list of dependencies.
    """
    mod_tree = mod_tree or set()
    kmod, modinfo = _get_kmod_info(self, kmod)

    # Get kernel module dependencies, softedeps if not ignored
    dependencies = []
    if harddeps := modinfo["depends"]:
        dependencies += harddeps

    if sofdeps := modinfo["softdep"]:
        if self.get("kmod_ignore_softdeps", False):
            self.logger.warning("[%s] Soft dependencies were detected, but are being ignored: %s" % (kmod, sofdeps))
        else:
            dependencies += sofdeps

    # Iterate over module dependencies, skipping them if they are already in the mod_tree (to prevent infinite recursion)
    # If the module isn't builtin or ignored, add it to the kernel_modules list and process its dependencies
    for dependency in dependencies:
        if dependency in mod_tree:
            self.logger.debug("[%s] Dependency is already in mod_tree: %s" % (kmod, dependency))
            continue
        dependency, dep_modinfo = _get_kmod_info(self, dependency)  # Get modinfo for the dependency
        if dependency in self["kmod_ignore"]:  # Don't add modules with ignored dependencies
            if dep_modinfo["filename"] == "(builtin)":
                self.logger.debug("[%s] Ignored dependency is a built-in module: %s" % (kmod, dependency))
                continue
            # If modinfo doesn't exist, or it's not builtin, simply raise an ignored module error
            raise IgnoredModuleError("[%s] Kernel module dependency is in ignore list: %s" % (kmod, dependency))
        if dependency in self["kernel_modules"]:
            self.logger.debug("[%s] Dependency is already in kernel_modules: %s" % (kmod, dependency))
            continue
        mod_tree.add(dependency)
        try:
            self.logger.debug("[%s] Processing dependency: %s" % (kmod, dependency))
            _process_kmod_dependencies(self, dependency, mod_tree)
        except BuiltinModuleError as e:
            self.logger.debug(e)
            continue
        self["kernel_modules"] = dependency

    if modinfo["filename"] == "(builtin)":  # for built-in modules, just add firmware and return
        _add_kmod_firmware(self, kmod)
        raise BuiltinModuleError("Not adding built-in module to dependencies: %s" % kmod)

    return kmod, dependencies


def add_kmod_deps(self):
    """Adds all kernel modules to the initramfs dependencies.
    Always attempt to add firmware, continuing if no_kmod is set.
    If they are compressed with a supported extension, they are decompressed before being added.

    Adds modprobe to the binaries list if no_kmod is not set.
    """
    if not self["no_kmod"]:
        self.logger.debug("Adding modprobe to binaries list.")
        self["binaries"] = "modprobe"
    else:
        self.logger.info("no_kmod is enabled, skipping adding modprobe to binaries list.")

    for kmod in self["kernel_modules"]:
        if self.get("kernel_version"):
            _add_kmod_firmware(self, kmod)
        else:
            self.logger.warning(
                f"Kernel version is not set, skipping firmware detection for kmod: {c_(kmod, 'yellow')}"
            )
        # if no_kmod is set, continue and check for the firmware of the next module
        if self["no_kmod"]:
            continue

        # Add the kmod file to the initramfs dependenceis
        kmod, modinfo = _get_kmod_info(self, kmod)
        filename = modinfo["filename"]
        if filename.endswith(".ko"):
            self["dependencies"] = filename
        elif filename.endswith(".ko.xz"):
            self["xz_dependencies"] = filename
        elif filename.endswith(".ko.zstd") or filename.endswith(".ko.zst"):
            self["zstd_dependencies"] = filename
        elif filename.endswith(".ko.gz"):
            self["gz_dependencies"] = filename
        else:
            self.logger.warning("[%s] Unknown kmod extension: %s" % (kmod, filename))
            self["dependencies"] = filename


def process_ignored_module(self, module: str) -> None:
    """Processes an ignored module."""
    self.logger.debug("Removing kernel module from all lists: %s", module)
    for key in ["kmod_init", "kernel_modules", "_kmod_auto"]:
        if module in self[key]:
            if key == "kmod_init":
                try:
                    module, modinfo = _get_kmod_info(self, module)
                    if modinfo["filename"] == "(builtin)":
                        self.logger.debug("Removing built-in module from kmod_init: %s" % module)
                except DependencyResolutionError:
                    if module == "zfs":
                        self.logger.critical("ZFS module is required but missing.")
                        self.logger.critical("Please build/install the required kmods before running this script.")
                        self.logger.critical("Detected kernel version: %s" % self["kernel_version"])
                        # https://github.com/projg2/installkernel-gentoo/commit/1c70dda8cd2700e5306d2ed74886b66ad7ccfb42
                        exit(77)
                    else:
                        raise MissingModuleError("Required module cannot be imported and is not builtin: %s" % module)
            else:
                self.logger.debug("Removing ignored kernel module from %s: %s" % (key, module))
            self[key].remove(module)
            self["_kmod_removed"] = module


def process_ignored_modules(self) -> None:
    """Processes all ignored modules."""
    for module in self["kmod_ignore"]:
        process_ignored_module(self, module)


def _process_optional_modules(self) -> None:
    """Processes optional kernel modules."""
    for kmod in self["kmod_init_optional"]:
        if kmod in self["kmod_init"]:
            self.logger.debug(f"Optional kmod_init module is already in kmod_init: {c_(kmod, 'yellow', bold=True)}")
            continue
        try:
            kmod, dependencies = _process_kmod_dependencies(self, kmod)
            self["kmod_init"] = kmod  # add to kmod_init so it will be loaded
        except IgnoredModuleError as e:
            self.logger.warning(e)
        except BuiltinModuleError:
            self.logger.debug(f"Optional kmod_init module is built-in, skipping: {c_(kmod, 'yellow')}")
            continue
        except DependencyResolutionError as e:
            self.logger.warning(
                f"[{c_(kmod, 'yellow', bold=True)}] Failed to process optional kernel module dependencies: {e}"
            )


@unset("no_kmod", "no_kmod is enabled, skipping.", log_level=30)
def process_modules(self) -> None:
    """Processes all kernel modules, adding dependencies to the initramfs."""
    _process_optional_modules(self)
    self.logger.debug("Processing kernel modules: %s" % self["kernel_modules"])
    for kmod in self["kernel_modules"].copy():
        """ Process all kernel modules
        for kmod_init modules, log an error if info can't be retreived, but continue processing.
        in successful cases, continue, if he module processing fails, add to the ignore list.
        Later, when ignored modules are processed, an exception is raised if the module is required.
        """
        self.logger.debug("Processing kernel module: %s" % kmod)
        try:
            _process_kmod_dependencies(self, kmod)
            continue
        except BuiltinModuleError:
            if kmod in self["kmod_init"]:
                self.logger.debug("Removing built-in module from kmod_init: %s" % kmod)
                self["kmod_init"].remove(kmod)
            self.logger.debug("Removing built-in module from kernel_modules: %s" % kmod)
            self["kernel_modules"].remove(kmod)
            continue  # Don't add built-in modules to the ignore list
        except IgnoredModuleError as e:
            self.logger.warning(e)
        except DependencyResolutionError as e:
            if kmod in self["kmod_init"]:
                # Once optional modules are fully implemented, this should raise an exception instead
                self.logger.error("[%s] Failed to get modinfo for init kernel module: %s" % (kmod, e))
            self.logger.debug("[%s] Failed to get modinfo for kernel module: %s" % (kmod, e))
        self["kmod_ignore"] = kmod

    for kmod in self["_kmod_auto"]:
        """ Do similar for automatic modules, but log warnings insead of errors if dependencies are missing. """
        if kmod in self["kernel_modules"]:
            self.logger.debug("Autodetected module is already in kernel_modules: %s" % kmod)
            continue
        self.logger.debug("Processing autodetected kernel module: %s" % kmod)
        try:
            kmod_name, dependencies = _process_kmod_dependencies(self, kmod)
            self["kmod_init"] = kmod_name
            continue
        except BuiltinModuleError:
            continue  # Don't add built-in modules to the ignore list
        except IgnoredModuleError as e:
            self.logger.debug(e)  # when autodetected modules are ignored, only debug log
        except (
            DependencyResolutionError
        ) as e:  # log a warning, not error or exception when autodetected modules have missing deps
            self.logger.warning("[%s] Failed to process autodetected kernel module dependencies: %s" % (kmod, e))
        self["kmod_ignore"] = kmod


@contains("kernel_version", "Kernel version is not set, skipping kernel version check.", log_level=30)
def check_kver(self) -> str:
    """Returns posix shell lines to check that the defined kernel version matches the running kernel version."""
    return f"""
    running_kver=$(awk '{{print $3}}' /proc/version)
    if [ "$running_kver" != "{self["kernel_version"]}" ]; then
        eerror "Running kernel version ($running_kver) does not match the defined kernel version ({self["kernel_version"]})"
        eerror "Please ensure the correct kernel version is being booted."
    fi
    """


@contains("kmod_init", "No kernel modules to load.", log_level=30)
def load_modules(self) -> str | None:
    """Creates a shell function which loads all kernel modules in kmod_init."""
    init_kmods = ", ".join(self["kmod_init"])
    included_kmods = ", ".join(list(set(self["kernel_modules"]) ^ set(self["kmod_init"])))
    removed_kmods = ", ".join(self["_kmod_removed"])
    if self["no_kmod"]:
        if included_kmods or init_kmods:
            self.logger.warning(
                "no_kmod is enabled, but kernel modules are set, ensure the following kernel modules are built into the kernel:"
            )
            self.logger.warning(f"Init kernel modules: {c_(init_kmods, 'red', bold=True)}")
            self.logger.warning(f"Included kernel modules: {c_(included_kmods, 'red', bold=True)}")
        return None

    self.logger.info(f"Init kernel modules: {c_(init_kmods, 'magenta', bright=True, bold=True)}")
    if included_kmods:
        self.logger.info(f"Included kernel modules: {c_(included_kmods, 'magenta')}")

    if removed_kmods:
        self.logger.warning("Ignored kernel modules: %s" % c_(removed_kmods, "red", bold=True))

    module_list = " ".join(self["kmod_init"])
    return f"""
    if check_var quiet ; then
        modprobe -aq {module_list}
    else
        einfo "Loading kernel modules: {module_list}"
        modprobe -av {module_list}
    fi
    """
