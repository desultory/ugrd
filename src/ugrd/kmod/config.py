__author__ = "desultory"
__version__ = "0.1.0"

import gzip
import os
from pathlib import Path
from typing import Optional


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
                "Hint: install the kernel headers/source to enable kernel config checks: %s"
                % hint.format(kver=kver)
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
    opener = gzip.open if path.suffix == ".gz" else open
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
    self.logger.debug("Parsed %d kernel config options from: %s" % (len(options), path))
    return options


def find_kernel_config(self) -> None:
    """Locates the target kernel's .config and caches its parsed contents.

    Sets:
        self["_kernel_config_file"]    -> Path to the file (or unset if not found)
        self["_kernel_config_options"] -> dict of parsed options (or unset/empty)

    Resilient: never raises. If no config is found, logs a warning plus a
    distro-specific tip, and consumers fall back to "couldn't verify".
    """
    if user_override := self.get("kernel_config_file"):
        override_path = Path(user_override)
        if override_path.exists():
            self.logger.info("Using user-provided kernel config: %s" % override_path)
            self["_kernel_config_file"] = override_path
            self["_kernel_config_options"] = _parse_kernel_config(self, override_path)
            return
        self.logger.warning(
            "kernel_config_file is set but does not exist: %s; falling back to autodetection." % override_path
        )

    kver = self.get("kernel_version")
    if not kver:
        self.logger.debug("Skipping kernel config lookup: kernel_version is not set.")
        return

    tried: list[str] = []
    for candidate in _candidate_paths(kver):
        tried.append(str(candidate))
        if candidate.exists() and candidate.is_file():
            self.logger.info("Found kernel config: %s" % candidate)
            self["_kernel_config_file"] = candidate
            try:
                self["_kernel_config_options"] = _parse_kernel_config(self, candidate)
            except OSError as e:
                self.logger.warning("Failed to read kernel config '%s': %s" % (candidate, e))
                continue
            return

    # /proc/config.gz: only valid when building for the running kernel.
    proc_config = Path("/proc/config.gz")
    use_proc = self.get("kernel_config_use_proc", True)
    if use_proc and proc_config.exists():
        running = os.uname().release
        if kver == running:
            self.logger.info("Using /proc/config.gz (target kernel matches running kernel %s)" % running)
            self["_kernel_config_file"] = proc_config
            try:
                self["_kernel_config_options"] = _parse_kernel_config(self, proc_config)
                return
            except OSError as e:
                self.logger.warning("Failed to read /proc/config.gz: %s" % e)
        else:
            self.logger.debug(
                "Ignoring /proc/config.gz: running kernel is %s, target is %s." % (running, kver)
            )
            tried.append("/proc/config.gz (skipped: target != running)")

    self.logger.warning(
        "Kernel config for '%s' not found. Tried:\n  %s" % (kver, "\n  ".join(tried))
    )
    _emit_install_hint(self, kver)


def _normalize_option(option: str) -> str:
    option = option.upper()
    if not option.startswith("CONFIG_"):
        option = "CONFIG_" + option
    return option


def check_kernel_config(self, option: str) -> Optional[bool]:
    """Returns True if CONFIG_<option> is set to 'y' or 'm', False if 'n' (or absent),
    or None when the kernel config wasn't available (caller should assume support).
    """
    options = self.get("_kernel_config_options")
    if not options:
        return None
    value = options.get(_normalize_option(option), "n")
    return value in ("y", "m")


def get_kernel_config_value(self, option: str) -> Optional[str]:
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
