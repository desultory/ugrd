__author__ = "desultory"
__version__ = "3.1.0"

from pathlib import Path
from subprocess import run

from ugrd.kmod import BuiltinModuleError, DependencyResolutionError, IgnoredModuleError, _normalize_kmod_name
from zenlib.util import colorize, contains, unset

MODULE_METADATA_FILES = ["modules.order", "modules.builtin", "modules.builtin.modinfo"]


def _process_kernel_modules_multi(self, module: str) -> None:
    """Adds kernel modules to self['kernel_modules']."""
    module = _normalize_kmod_name(module)
    if module in self["kmod_ignore"]:
        self.logger.debug("[%s] Module is in the ignore list." % module)
        self["_kmod_removed"] = module
        return

    self.logger.debug("Adding kernel module to kernel_modules: %s", module)
    self["kernel_modules"].append(module)


def _process_kmod_init_multi(self, module: str) -> None:
    """Adds init modules to self['kernel_modules']."""
    module = _normalize_kmod_name(module)
    if module in self["kmod_ignore"]:
        raise IgnoredModuleError("kmod_init module is in the ignore list: %s" % module)
    self["kmod_init"].append(module)
    self.logger.debug("Adding kmod_init module to kernel_modules: %s", module)
    self["kernel_modules"] = module


def _process__kmod_auto_multi(self, module: str) -> None:
    """Adds autodetected modules to self['kernel_modules']."""
    module = _normalize_kmod_name(module)
    if module in self["kmod_ignore"]:
        self.logger.debug("Autodetected module is in the ignore list: %s" % module)
        self["_kmod_removed"] = module
        return
    self.logger.debug("Adding autodetected kernel module to kernel_modules: %s", module)
    self["_kmod_auto"].append(module)


def _get_kmod_info(self, module: str):
    """
    Runs modinfo on a kernel module, parses the output and stored the results in self['_kmod_modinfo'].
    !!! Should be run after metadata is processed so the kver is set properly !!!
    """
    module = _normalize_kmod_name(module)
    if module in self["_kmod_modinfo"]:
        return self.logger.debug("[%s] Module info already exists." % module)
    args = ["modinfo", module, "--set-version", self["kernel_version"]]

    try:
        self.logger.debug("[%s] Modinfo command: %s" % (module, " ".join(args)))
        cmd = run(args, capture_output=True)
    except RuntimeError as e:
        raise DependencyResolutionError("[%s] Failed to run modinfo command: %s" % (module, " ".join(args))) from e

    if not cmd.stdout and cmd.stderr:
        raise DependencyResolutionError("[%s] Modinfo returned no output." % module)

    module_info = {}
    for line in cmd.stdout.decode().split("\n"):
        line = line.strip()
        if line.startswith("filename:"):
            module_info["filename"] = line.split()[1]
        elif line.startswith("depends:") and line != "depends:":
            if "," in line:
                module_info["depends"] = _normalize_kmod_name(line.split(":")[1].lstrip().split(","))
            else:
                module_info["depends"] = _normalize_kmod_name([line.split()[1]])
        elif line.startswith("softdep:"):
            if "softdep" not in module_info:
                module_info["softdep"] = []
            module_info["softdep"] += line.split()[2::2]
        elif line.startswith("firmware:"):
            # Firmware is a list, so append to it, making sure it exists first
            if "firmware" not in module_info:
                module_info["firmware"] = []
            module_info["firmware"] += line.split()[1:]

    if not module_info.get("filename"):
        raise DependencyResolutionError("[%s] Failed to process modinfo output: %s" % (module, cmd.stdout.decode()))

    self.logger.debug("[%s] Module info: %s" % (module, module_info))
    self["_kmod_modinfo"][module] = module_info


@contains("kmod_autodetect_lspci", "kmod_autodetect_lspci is not enabled, skipping.")
def _autodetect_modules_lspci(self) -> None:
    """Gets the name of all kernel modules being used by hardware visible in lspci -k."""
    try:
        cmd = self._run(["lspci", "-k"])
    except RuntimeError as e:
        raise DependencyResolutionError("Failed to get list of kernel modules") from e
    lspci_kmods = set()
    # Iterate over all output lines
    for line in cmd.stdout.decode("utf-8").split("\n"):
        # If the line contains the string 'Kernel modules:' or 'Kernel driver in use:', it contains the name of a kernel module
        if "Kernel modules:" in line or "Kernel driver in use:" in line:
            module = line.split(":")[1]
            if "," in module:
                # If there are multiple modules, split them and add them to the module set
                for module in module.split(","):
                    lspci_kmods.add(module.strip())
            else:
                lspci_kmods.add(module.strip())

    self["_kmod_auto"] = list(lspci_kmods)


@contains("kmod_autodetect_lsmod", "kmod_autodetect_lsmod is not enabled, skipping.")
def _autodetect_modules_lsmod(self) -> None:
    """Gets the name of all currently used kernel modules."""
    from platform import uname

    if self.get("kernel_version") and self["kernel_version"] != uname().release:
        self.logger.warning(
            "Kernel version is set to %s, but the current kernel version is %s"
            % (self["kernel_version"], uname().release)
        )

    with open("/proc/modules", "r") as f:
        for module in f.readlines():
            self["_kmod_auto"] = module.split()[0]


@unset("no_kmod", "no_kmod is enabled, skipping.", log_level=30)
@contains("hostonly", "Skipping kmod autodetection, hostonly is disabled.", log_level=30)
def autodetect_modules(self) -> None:
    """Autodetects kernel modules from lsmod and/or lspci -k."""
    if not self["kmod_autodetect_lsmod"] and not self["kmod_autodetect_lspci"]:
        self.logger.debug("No autodetection methods are enabled.")
        return
    _autodetect_modules_lsmod(self)
    _autodetect_modules_lspci(self)
    if self["_kmod_auto"]:
        self.logger.info("Autodetected kernel modules: %s" % colorize(", ".join(self["_kmod_auto"], "cyan")))
    else:
        self.logger.warning("No kernel modules were autodetected.")


def _find_kernel_image(self) -> None:
    """Finds the kernel image,
    Searches /boot, then /efi for prefixes 'vmlinuz', 'linux', and 'bzImage'.
    Searches for the file with the prefix, then files starting with the prefix and a hyphen.
    If multiple files are found, uses the last modified."""

    def search_prefix(prefix: str) -> Path:
        for path in ["/boot", "/efi"]:
            kernel_path = (Path(path) / f"{prefix}").resolve()
            if kernel_path.exists():
                return kernel_path
            kernel_path = None
            for file in Path(path).glob(f"{prefix}-*"):
                file = file.resolve()
                if not file.is_file():
                    continue
                if not kernel_path:
                    kernel_path = file
                elif file.stat().st_mtime > kernel_path.stat().st_mtime:
                    kernel_path = file
            if kernel_path:
                return kernel_path
        self.logger.debug("Failed to find kernel image with prefix: %s" % prefix)

    for prefix in ["vmlinuz", "linux", "bzImage"]:
        if kernel_path := search_prefix(prefix):
            self.logger.info("Detected kernel image: %s" % (colorize(kernel_path, "cyan")))
            return kernel_path
    raise DependencyResolutionError("Failed to find kernel image")


def _get_kver_from_header(self) -> str:
    """Tries to read the kernel version from the kernel header.
    The offset of the kernel version is stored in 2 bytes at 0x020E.
    An additional sector is skipped, so the offset is increased by 512.
    The version string can be up to 127 bytes long and is null-terminated.
    https://www.kernel.org/doc/html/v6.7/arch/x86/boot.html#the-real-mode-kernel-header
    """
    from struct import unpack

    kernel_path = _find_kernel_image(self)
    kver_offset = unpack("<h", kernel_path.read_bytes()[0x020E:0x0210])[0] + 512
    header = kernel_path.read_bytes()[kver_offset : kver_offset + 127]
    # Cut at the first null byte, decode to utf-8, and split at the first space
    kver = header[: header.index(0)].decode("utf-8").split()[0]
    return kver


def _process_kernel_version(self, kver: str) -> None:
    """Sets the kerenl_version, checks that the kmod directory exits, sets the _kmod_dir variable."""
    if self["no_kmod"]:
        self.logger.error("kernel_version is set, but no_kmod is enabled.")
    kmod_dir = Path("/lib/modules") / kver
    if not kmod_dir.exists():
        if self["no_kmod"]:
            return self.logger.warning("[%s] Kernel module directory does not exist, but no_kmod is set." % kver)
        raise DependencyResolutionError(f"Kernel module directory does not exist for kernel: {kver}")

    self.data["kernel_version"] = kver
    self.data["_kmod_dir"] = kmod_dir


def _handle_arch_kernel(self) -> None:
    """Checks that an arch package owns the kernel version directory."""
    kernel_path = Path("/lib/modules") / self["kernel_version"] / "vmlinuz"
    try:
        cmd = self._run(["pacman", "-Qqo", kernel_path])
        if not self["out_file"]:
            self["out_file"] = f"/boot/initramfs-{cmd.stdout.decode().strip()}.img"
            self.logger.info("Setting out_file to: %s" % colorize(self["out_file"], "green", bold=True))
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
    self.logger.info("Detected kernel version: %s" % colorize(self["kernel_version"], "cyan", bright=True))


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
    """Adds firmware files for the specified kernel module to the initramfs."""
    kmod = _normalize_kmod_name(kmod)
    if kmod not in self["_kmod_modinfo"]:
        raise DependencyResolutionError("Kernel module info does not exist: %s" % kmod)

    if self["_kmod_modinfo"][kmod].get("firmware") and not self["kmod_pull_firmware"]:
        self.logger.warning("[%s] Kernel module has firmware files, but kmod_pull_firmware is not set." % kmod)

    if not self["_kmod_modinfo"][kmod].get("firmware") or not self.get("kmod_pull_firmware"):
        return

    for firmware in self["_kmod_modinfo"][kmod]["firmware"]:
        _add_firmware_dep(self, kmod, firmware)


def _add_firmware_dep(self, kmod: str, firmware: str) -> None:
    """Adds a kernel module firmware file to the initramfs dependencies."""
    kmod = _normalize_kmod_name(kmod)
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


def _process_kmod_dependencies(self, kmod: str) -> None:
    """Processes a kernel module's dependencies."""
    kmod = _normalize_kmod_name(kmod)
    _get_kmod_info(self, kmod)

    if self["_kmod_modinfo"][kmod]["filename"] == "(builtin)":  # for built-in modules, just add firmware and return
        _add_kmod_firmware(self, kmod)
        raise BuiltinModuleError("Not adding built-in module to dependencies: %s" % kmod)

    # Add dependencies of the module
    dependencies = []
    if harddeps := self["_kmod_modinfo"][kmod].get("depends"):
        dependencies += harddeps

    if sofdeps := self["_kmod_modinfo"][kmod].get("softdep"):
        if self.get("kmod_ignore_softdeps", False):
            self.logger.warning("[%s] Soft dependencies were detected, but are being ignored: %s" % (kmod, sofdeps))
        else:
            dependencies += sofdeps

    for dependency in dependencies:
        if dependency in self["kmod_ignore"]:  # Don't add modules with ignored dependencies
            _get_kmod_info(self, dependency)  # Make sure modinfo is queried in case it's built-in
            if modinfo := self["_kmod_modinfo"].get(dependency):
                if modinfo["filename"] == "(builtin)":  # If it's ignored because builtin, that's fine
                    self.logger.debug("[%s] Ignored dependency is a built-in module: %s" % (kmod, dependency))
                    continue
            # If modinfo doesn't exist, or it's not builtin, simply raise an ignored module error
            raise IgnoredModuleError("[%s] Kernel module dependency is in ignore list: %s" % (kmod, dependency))
        if dependency in self["kernel_modules"]:
            self.logger.debug("[%s] Dependency is already in kernel_modules: %s" % (kmod, dependency))
            continue
        try:
            self.logger.debug("[%s] Processing dependency: %s" % (kmod, dependency))
            _process_kmod_dependencies(self, dependency)
        except BuiltinModuleError as e:
            self.logger.debug(e)
            continue
        self["kernel_modules"] = dependency

    # Process firmware now that dependencies are resolved
    _add_kmod_firmware(self, kmod)

    # Add the kmod file to the initramfs dependenceis
    filename = self["_kmod_modinfo"][kmod]["filename"]
    if filename.endswith(".ko"):
        self["dependencies"] = filename
    elif filename.endswith(".ko.xz"):
        self["xz_dependencies"] = filename
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
                if module in self["_kmod_modinfo"] and self["_kmod_modinfo"][module]["filename"] == "(builtin)":
                    self.logger.debug("Removing built-in module from kmod_init: %s" % module)
                else:
                    raise ValueError("Required module cannot be imported and is not builtin: %s" % module)
            else:
                self.logger.debug("Removing ignored kernel module from %s: %s" % (key, module))
            self[key].remove(module)
            self["_kmod_removed"] = module


def process_ignored_modules(self) -> None:
    """Processes all ignored modules."""
    for module in self["kmod_ignore"]:
        process_ignored_module(self, module)


@unset("no_kmod", "no_kmod is enabled, skipping.", log_level=30)
def process_modules(self) -> None:
    """Processes all kernel modules, adding dependencies to the initramfs."""
    self.logger.debug("Processing kernel modules: %s" % self["kernel_modules"])
    for kmod in self["kernel_modules"].copy():
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
            self.logger.info(e)
        except DependencyResolutionError as e:
            if kmod in self["kmod_init"]:
                self.logger.warning("[%s] Failed to get modinfo for init kernel module: %s" % (kmod, e))
            self.logger.debug("[%s] Failed to get modinfo for kernel module: %s" % (kmod, e))
        self["kmod_ignore"] = kmod

    for kmod in self["_kmod_auto"]:
        if kmod in self["kernel_modules"]:
            self.logger.debug("Autodetected module is already in kernel_modules: %s" % kmod)
            continue
        self.logger.debug("Processing autodetected kernel module: %s" % kmod)
        try:
            _process_kmod_dependencies(self, kmod)
            self["kmod_init"] = kmod
            continue
        except BuiltinModuleError:
            continue  # Don't add built-in modules to the ignore list
        except IgnoredModuleError as e:
            self.logger.debug(e)
        except DependencyResolutionError as e:
            self.logger.warning("[%s] Failed to process autodetected kernel module dependencies: %s" % (kmod, e))
        self["kmod_ignore"] = kmod


@contains("kmod_init", "No kernel modules to load.", log_level=30)
def load_modules(self) -> None:
    """Creates a bash script which loads all kernel modules in kmod_init."""
    self.logger.info(
        "Init kernel modules: %s" % colorize(", ".join(self["kmod_init"]), "magenta", bright=True, bold=True)
    )
    if included_kmods := list(set(self["kernel_modules"]) ^ set(self["kmod_init"])):
        self.logger.info("Included kernel modules: %s" % colorize(", ".join(included_kmods), "magenta"))
    if removed_kmods := self.get("_kmod_removed"):
        self.logger.warning("Ignored kernel modules: %s" % colorize(", ".join(removed_kmods), "red", bold=True))

    module_list = " ".join(self["kmod_init"])
    return [
        "if check_var quiet ; then",
        "    modprobe -aq %s" % module_list,
        "else",
        '    einfo "Loading kernel modules: %s"' % module_list,
        "    modprobe -av %s" % module_list,
        "fi",
    ]
