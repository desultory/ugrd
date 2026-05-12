__author__ = "desultory"
__version__ = "3.10.0"

from importlib.util import find_spec
from pathlib import Path

from pycpio.cpio.symlink import CPIO_Symlink
from zenlib.util import colorize, contains, unset

from ugrd.kmod.config import check_kernel_config

# Fallback chain per user request. pycpio only supports xz and zstd.
# Order: most preferred first; "false" means "no compression".
_COMPRESSION_FALLBACK = {
    "true": ("xz", "zstd", "false"),
    "xz": ("xz", "zstd", "false"),
    "zstd": ("zstd", "xz", "false"),
    "false": ("false",),
}


@contains("check_cpio")
def check_cpio_deps(self) -> str:
    """Checks that all dependenceis are in the generated CPIO file."""
    for dep in self["dependencies"]:
        _check_in_cpio(self, dep)
    return "All dependencies found in CPIO."


@contains("check_cpio")
def check_cpio_funcs(self) -> str:
    """Checks that all included functions are in the profile included in the generated CPIO file."""
    sh_func_names = [func + "() {" for func in self.included_functions]
    _check_in_cpio(self, "etc/profile", sh_func_names)
    return "All functions found in CPIO."


@contains("check_in_cpio")
@contains("check_cpio")
def check_in_cpio(self) -> str:
    """Checks that all required files and lines are in the generated CPIO file."""
    for file, lines in self["check_in_cpio"].items():
        _check_in_cpio(self, file, lines)
    return "All files and lines found in CPIO."


def _check_in_cpio(self, file, lines=[], quiet=False) -> None:
    """Checks that the file is in the CPIO archive, and it contains the specified lines."""
    cpio = self._cpio_archive
    file = str(file).lstrip("/")  # Normalize as it may be a path
    self.logger.debug("Checking CPIO for dependency: %s" % file)
    if file not in cpio.entries:
        fp = Path(file)
        while str(fp) not in ["/", "."]:
            fp = fp.parent
            if str(fp) not in cpio.entries:
                continue

            if isinstance(cpio.entries[str(fp)], CPIO_Symlink):
                self.logger.debug("Resolving CPIO symlink: %s" % fp)
                return _check_in_cpio(self, cpio.entries[str(fp)].data.decode("ascii").rstrip("\0"), lines, quiet=True)

        if not quiet:
            self.logger.warning("CPIO entries:\n%s" % "\n".join(cpio.entries.keys()))
        raise FileNotFoundError("File not found in CPIO: %s" % file)
    else:
        self.logger.debug("File found in CPIO: %s" % file)

    if lines:
        entry_data = cpio.entries[file].data.decode().splitlines()
        for line in lines:
            if line not in entry_data:
                raise FileNotFoundError("Line not found in CPIO: %s" % line)
            else:
                self.logger.debug("Line found in CPIO: %s" % line)


def _compression_unavailable_reason(self, name: str) -> str | None:
    """Returns None when the compression can be used, otherwise a human-readable reason."""
    if name == "false":
        return None
    if name == "zstd" and find_spec("zstandard") is None:
        return "Python module 'zstandard' is not installed"
    kernel_support = check_kernel_config(self, "RD_" + name.upper())
    if kernel_support is False:
        return "kernel does not have CONFIG_RD_%s enabled" % name.upper()
    if kernel_support is None:
        self.logger.debug(
            "Kernel config not available; assuming CONFIG_RD_%s support for '%s'." % (name.upper(), name)
        )
    return None


def select_cpio_compression(self) -> None:
    """Picks the best CPIO compression based on user preference, kernel CONFIG_RD_*
    options, and the availability of the 'zstandard' Python module.

    Priorities:
        true  -> xz, zstd, no compression
        xz    -> xz, zstd, no compression
        zstd  -> zstd, xz, no compression
        false -> no compression

    Warns when the explicitly requested compression has to be downgraded so the
    user notices before booting into an unbootable image.
    """
    raw = str(self.get("cpio_compression", "true")).lower()
    if raw not in _COMPRESSION_FALLBACK:
        self.logger.warning(
            "Unknown cpio_compression value '%s'; supported values: true, xz, zstd, false. Using 'true'."
            % raw
        )
        raw = "true"

    chain = _COMPRESSION_FALLBACK[raw]
    selected = None
    for candidate in chain:
        reason = _compression_unavailable_reason(self, candidate)
        if reason is None:
            selected = candidate
            break
        if candidate == raw:
            self.logger.warning("Requested CPIO compression '%s' is not available: %s." % (raw, reason))
        else:
            self.logger.warning("CPIO compression fallback '%s' is not available: %s." % (candidate, reason))

    if selected is None:  # "false" is always last so this should not happen
        selected = "false"

    if raw in ("xz", "zstd") and selected != raw:
        self.logger.warning(
            "Falling back to CPIO compression '%s' instead of '%s'." % (selected, raw)
        )
    elif raw == "true" and selected == "false":
        self.logger.warning("No supported CPIO compression available; building uncompressed initramfs.")

    self["cpio_compression"] = selected
    self.logger.info("Selected CPIO compression: %s" % colorize(selected, "cyan", bold=True))


@unset("out_file")
def get_archive_name(self) -> None:
    """Determines the filename for the output CPIO archive based on the current configuration.
    Sets the 'out_file' key in the configuration dictionary.
    """
    if self.get("kmod_init") and self.get("kernel_version"):
        out_file = f"ugrd-{self['kernel_version']}.cpio"
    else:
        out_file = "ugrd.cpio"

    compression_type = self.get("cpio_compression")
    if compression_type and str(compression_type).lower() != "false":
        out_file += f".{compression_type}"
    self["out_file"] = out_file


def make_cpio(self) -> None:
    """
    Populates the CPIO archive using the build directory,
    toggles the deduplication setting based on cpio_deduplicate,
    writes it to the output file, and rotates the output file if necessary.
    Creates device nodes in the CPIO archive if make_nodes is False. (make_nodes will create actual files instead)
    Raises FileNotFoundError if the output directory does not exist.
    """
    cpio = self._cpio_archive
    cpio.deduplicate = self["cpio_deduplicate"]
    cpio.append_recursive(self._get_build_path("/"), relative=True)

    if not self.get("make_nodes"):
        for node in self["nodes"].values():
            self.logger.debug("Adding CPIO node: %s" % node)
            cpio.add_chardev(name=node["path"], mode=node["mode"], major=node["major"], minor=node["minor"])

    out_cpio = self._get_out_path(self["out_file"])
    if not out_cpio.parent.exists():
        self._mkdir(out_cpio.parent, resolve_build=False)

    if out_cpio.exists():
        if self["cpio_rotate"]:
            self._rotate_old(out_cpio)
        elif self["clean"]:
            self.logger.warning("Removing existing file: %s" % colorize(out_cpio, "red", bold=True, bright=True))
            out_cpio.unlink()
        else:
            raise FileExistsError("File already exists, and cleaning/rotation are disabled: %s" % out_cpio)

    cpio.write_cpio_file(out_cpio, compression=self["cpio_compression"], _log_bump=-10)
