__version__ = "0.3.0"

from pathlib import Path
from zenlib.util import contains


@contains("check_included_funcs", "Skipping included funcs check", log_level=30)
def check_included_funcs(self):
    """Ensures required functions are included in the build dir."""
    bash_func_names = [func + "() {\n" for func in self.included_functions]
    _check_in_file(self, "/etc/profile", bash_func_names)
    return "All functions found in the build dir."


@contains("check_in_file", "Skipping in file check")
def check_in_file(self):
    """Runs all 'check_in_file' checks."""
    for file, lines in self["check_in_file"].items():
        _check_in_file(self, file, lines)
    return "All 'check_in_file' checks passed"


def _check_in_file(self, file, lines):
    """Checks that all lines are in the file."""
    file = self._get_build_path(file)
    if not file.exists():
        raise ValueError("File '%s' does not exist" % file)

    with open(file, "r") as f:
        file_lines = f.readlines()

    for check_line in lines:
        if check_line not in file_lines:
            raise ValueError("Failed to find line '%s' in file '%s'" % (check_line, file))

def _find_in_mounts(self, file) -> str:
    """Checks if a file is under a defined mount.
    Returns the mount point if found, otherwise raises an error."""
    file_path = Path(file)
    while parent := file_path.parent:
        if str(parent) in ["/", "."]:
            raise ValueError("File '%s' not found in any mounts" % file)
        if str(parent).lstrip("/") in self.mounts:
            return str(parent).lstrip("/")
        file_path = parent


@contains("check_included_or_mounted")
def check_included_or_mounted(self):
    """Ensures these files are included in the initramfs, or would be available under a mount"""
    from ugrd.fs.cpio import _check_in_cpio
    for file in self["check_included_or_mounted"]:
        try:  # First check if it's in the cpio
            _check_in_cpio(self, file, quiet=True)
        except FileNotFoundError:  # Then check if it's under a mount
            mountpoint = _find_in_mounts(self, file)
            if not Path(file).exists():
                self.logger.error("File detected under mount '%s' but is not present: %s" % ( mountpoint, file))

    return "All included files were found."
