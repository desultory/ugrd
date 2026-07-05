__author__ = "desultory"
__version__ = "0.1.0"

from gzip import open as gzip_open
from os import uname
from pathlib import Path

from zenlib.util import colorize as c_

# Distro-aware search paths for the *target* kernel's .config.
# Each entry is a template containing {kver}. Tried in order; first hit wins.
_CONFIG_SEARCH_TEMPLATES = (
    "/lib/modules/{kver}/build/.config",        # Arch, Debian, Fedora (via headers/devel symlink)
    "/lib/modules/{kver}/source/.config",       # Gentoo (and others with split build/source)
    "/boot/config-{kver}",                      # Debian, Fedora, Ubuntu (shipped with linux-image)
    "/usr/src/linux-headers-{kver}/.config",    # Debian explicit
    "/usr/src/kernels/{kver}/.config",          # Fedora/RHEL explicit
    "/usr/src/linux-{kver}/.config",            # Gentoo explicit
)

# Resolved at runtime: /usr/src/linux is only used if its target matches kver.
_GENTOO_GENERIC_SYMLINK = Path("/usr/src/linux")

# Distros where we know /proc/config.gz is enabled out of the box.
# Used purely for the actionable tip; the runtime check is the file's existence.
_DISTRO_INSTALL_HINTS = {
    "arch": "pacman -S linux-headers (or the *-headers package matching your kernel)",
    "manjaro": "pacman -S linux-headers",
    "endeavouros": "pacman -S linux-headers",
    "debian": "apt install linux-headers-{kver}",
    "ubuntu": "apt install linux-headers-{kver}",
    "fedora": "dnf install kernel-devel-{kver}",
    "rhel": "dnf install kernel-devel-{kver}",
    "centos": "dnf install kernel-devel-{kver}",
    "gentoo": "ensure /usr/src/linux points to the source tree of {kver}, or install gentoo-sources",
}


def _read_os_release_ids() -> list[str]:
    """Returns the ID and ID_LIKE values from /etc/os-release, lowercased."""
    ids: list[str] = []
    try:
        with open("/etc/os-release", "r") as f:
            data = dict(
                line.rstrip().split("=", 1)
                for line in f
                if "=" in line and not line.startswith("#")
            )
    except OSError:
        return ids
    for key in ("ID", "ID_LIKE"):
        value = data.get(key, "").strip().strip('"').strip("'")
        if value:
            ids.extend(value.lower().split())
    return ids


def _emit_install_hint(self, kver: str) -> None:
    """Logs a distro-specific tip to help the user install the missing kernel config."""
    for distro_id in _read_os_release_ids():
        if hint := _DISTRO_INSTALL_HINTS.get(distro_id):
            self.logger.info(
                f"Hint: install the kernel headers/source to enable kernel config checks: "
                f"{c_(hint.format(kver=kver), 'cyan')}"
            )
            return


def _candidate_paths(kver: str) -> list[Path]:
    """Builds the ordered list of paths to probe for the kernel config."""
    paths = [Path(t.format(kver=kver)) for t in _CONFIG_SEARCH_TEMPLATES]

    # /usr/src/linux is the Gentoo "current source" symlink; only trust it when it
    # resolves to a directory whose name matches the target kver (linux-$KVER).
    if _GENTOO_GENERIC_SYMLINK.is_symlink():
        try:
            resolved = _GENTOO_GENERIC_SYMLINK.resolve(strict=False)
            if resolved.name == f"linux-{kver}":
                paths.append(resolved / ".config")
        except OSError:
            pass

    return paths


def _parse_kernel_config(self, path: Path) -> dict[str, str]:
    """Parses a kernel .config file (optionally gzipped) into a {OPTION: value} dict.
    Values are stored without quotes: 'y', 'm', 'n', integer strings, or string contents.
    Lines like '# CONFIG_FOO is not set' are recorded as 'n'.
    """
    opener = gzip_open if path.suffix == ".gz" else open
    options: dict[str, str] = {}
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                # "# CONFIG_FOO is not set"
                if line.endswith(" is not set"):
                    name = line[2:-len(" is not set")].strip()
                    if name.startswith("CONFIG_"):
                        options[name] = "n"
                continue
            if "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip()
            value = value.strip()
            if not name.startswith("CONFIG_"):
                continue
            if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                value = value[1:-1]
            options[name] = value
    self.logger.debug(f"Parsed {len(options)} kernel config options from: {c_(path, 'cyan')}")
    return options


def find_kernel_config(self) -> None:
    """Locates the target kernel's .config and caches its parsed contents.

    Sets:
        self["_kernel_config_file"]    -> Path to the file (or unset if not found)
        self["_kernel_config_options"] -> dict of parsed options (or unset/empty)

    Resilient: never raises. If no config is found, logs a warning plus a
    distro-specific tip, and consumers fall back to "couldn't verify".
    """
    # The default for an unset Path-typed parameter is PosixPath('.'), so a plain
    # truthy check would treat "not set" as if the user provided ".".
    user_override = self.get("kernel_config_file")
    if user_override and Path(user_override) != Path("."):
        override_path = Path(user_override)
        if override_path.is_file():
            self.logger.info(f"Using user-provided kernel config: {c_(override_path, 'cyan', bold=True)}")
            self["_kernel_config_file"] = override_path
            self["_kernel_config_options"] = _parse_kernel_config(self, override_path)
            return
        self.logger.warning(
            f"kernel_config_file is not a regular file, falling back to autodetection: "
            f"{c_(override_path, 'yellow', bold=True)}"
        )

    kver = self.get("kernel_version")
    if not kver:
        self.logger.debug("Skipping kernel config lookup: kernel_version is not set.")
        return

    tried: list[str] = []
    for candidate in _candidate_paths(kver):
        tried.append(str(candidate))
        if candidate.exists() and candidate.is_file():
            self.logger.info(f"Found kernel config: {c_(candidate, 'cyan', bold=True)}")
            self["_kernel_config_file"] = candidate
            try:
                self["_kernel_config_options"] = _parse_kernel_config(self, candidate)
            except OSError as e:
                self.logger.warning(f"[{c_(candidate, 'yellow', bold=True)}] Failed to read kernel config: {e}")
                continue
            return

    # /proc/config.gz: only valid when building for the running kernel.
    proc_config = Path("/proc/config.gz")
    use_proc = self.get("kernel_config_use_proc", True)
    if use_proc and proc_config.exists():
        running = uname().release
        if kver == running:
            self.logger.info(
                f"Using /proc/config.gz (target kernel matches running): {c_(running, 'magenta', bold=True)}"
            )
            self["_kernel_config_file"] = proc_config
            try:
                self["_kernel_config_options"] = _parse_kernel_config(self, proc_config)
                return
            except OSError as e:
                self.logger.warning(f"Failed to read /proc/config.gz: {e}")
        else:
            self.logger.debug(
                f"Ignoring /proc/config.gz, running kernel [{c_(running, 'cyan')}] does not match target "
                f"[{c_(kver, 'magenta')}]"
            )
            tried.append("/proc/config.gz (skipped: target != running)")

    self.logger.warning(
        f"Kernel config not found for kernel [{c_(kver, 'magenta', bold=True)}]. Tried:\n  "
        + "\n  ".join(tried)
    )
    _emit_install_hint(self, kver)


def _normalize_option(option: str) -> str:
    option = option.upper()
    if not option.startswith("CONFIG_"):
        option = "CONFIG_" + option
    return option


def check_kernel_config(self, option: str) -> bool | None:
    """Returns True if CONFIG_<option> is set to 'y' or 'm', False if 'n' (or absent),
    or None when the kernel config wasn't available (caller should assume support).
    """
    options = self.get("_kernel_config_options")
    if not options:
        return None
    value = options.get(_normalize_option(option), "n")
    return value in ("y", "m")


def get_kernel_config_value(self, option: str) -> str | None:
    """Returns the raw value of CONFIG_<option> (without surrounding quotes),
    or None when the config wasn't available or the option is unset.
    """
    options = self.get("_kernel_config_options")
    if not options:
        return None
    value = options.get(_normalize_option(option))
    if value in (None, "n"):
        return None
    return value
