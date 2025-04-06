__version__ = "0.4.1"

from pathlib import Path

from ugrd.exceptions import ValidationError
from zenlib.util import contains


@contains("check_included_funcs", "Skipping included funcs check", log_level=30)
def check_included_funcs(self):
    """Ensures required functions are included in the build dir."""
    sh_func_names = [func + "() {\n" for func in self.included_functions]
    _check_in_file(self, "/etc/profile", sh_func_names)
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
        raise FileNotFoundError("File '%s' does not exist" % file)

    with open(file, "r") as f:
        file_lines = f.readlines()

    for check_line in lines:
        if check_line not in file_lines:
            raise ValueError("Failed to find line '%s' in file '%s'" % (check_line, file))


def _find_mount_with_dest(self, check_path: Path) -> str:
    """Returns the mount name which has a destination matching the check path."""
    for mount_name, mount_config in self.mounts.items():
        if mount_config["destination"] == check_path:
            return mount_name


def _find_in_mounts(self, file) -> str:
    """Finds a corresponding mount config for a file, if defined."""
    file_path = Path(file)
    while parent := file_path.parent:
        if str(parent) in ["/", "."]:
            self.logger.warning("Configured mounts:\n%s" % self.mounts)
            raise ValidationError("File '%s' not found under any configured mounts" % file)

        if mount_name := _find_mount_with_dest(self, parent):
            return mount_name
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
                self.logger.error("File detected under mount '%s' but is not present: %s" % (mountpoint, file))

    return "All included files were found."


def check_init_order(self):
    """Ensures that init functions are ordered respecting import_order"""
    for hook, hook_funcs in self["imports"].items():  # Iterate through all imported functions
        if hook == "custom_init":
            continue  # Only one function should be in herE
        hook_funcs = [func.__name__ for func in hook_funcs]
        a = self["import_order"].get("after", {})
        after = {k: v for k, v in a.items() if k in hook_funcs and any(subv in hook_funcs for subv in v)}
        b = self["import_order"].get("before", {})
        before = {k: v for k, v in b.items() if k in hook_funcs and any(subv in hook_funcs for subv in v)}
        for func, targets in before.items():
            for target in targets:
                func_index = hook_funcs.index(func)
                try:
                    target_index = hook_funcs.index(target)
                except ValueError:
                    continue  # Ignore targets that are not imported
                if func_index > target_index:
                    raise ValidationError("[%s] Function must be before: %s" % (func, target))
        for func, targets in after.items():
            for target in targets:
                func_index = hook_funcs.index(func)
                try:
                    target_index = hook_funcs.index(target)
                except ValueError:
                    continue  # Ignore targets that are not imported
                if func_index < target_index:
                    raise ValidationError("[%s] Function must be after: %s" % (func, target))
