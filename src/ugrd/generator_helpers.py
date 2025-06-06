from pathlib import Path
from shutil import copy2
from subprocess import CompletedProcess, TimeoutExpired, run
from typing import Union
from uuid import uuid4

from zenlib.util import colorize as c_
from zenlib.util import pretty_print

from .exceptions import ValidationError

__version__ = "1.7.0"
__author__ = "desultory"


_RANDOM_BUILD_ID = str(uuid4())


def get_subpath(path: Path, subpath: Union[Path, str]) -> Path:
    """Returns the subpath of a path."""
    if not isinstance(subpath, Path):
        subpath = Path(subpath)

    if subpath.is_relative_to(path):
        return subpath

    if subpath.is_absolute():
        subpath = subpath.relative_to("/")
    return path / subpath


class GeneratorHelpers:
    """Mixin class for the InitramfsGenerator class."""

    def _get_out_path(self, path: Union[Path, str]) -> Path:
        """Takes a filename, if the out_dir is relative, returns the path relative to the tmpdir.
        If the out_dir is absolute, returns the path relative to the out_dir."""
        if self.out_dir.is_absolute():
            return get_subpath(self.out_dir, path)
        return get_subpath(get_subpath(self.tmpdir, self.out_dir), path)

    def _get_build_path(self, path: Union[Path, str]) -> Path:
        """Returns the path relative to the build directory, under the tmpdir.
        if random_build_dir is true, appends a uuid4() to the build directory."""
        if self.random_build_dir:
            build_dir = self.build_dir.with_name(self.build_dir.name + "-" + _RANDOM_BUILD_ID)
        else:
            build_dir = self.build_dir
        return get_subpath(get_subpath(self.tmpdir, build_dir), path)

    def _mkdir(self, path: Path, resolve_build=True) -> None:
        """
        Creates a directory within the build directory.
        If resolve_build is True, the path is resolved to the build directory.
        If not, the provided path is used as-is.
        """
        if resolve_build:
            path = self._get_build_path(path)

        self.logger.log(5, "Creating directory: %s" % path)
        if path.is_dir():
            path_dir = path.parent
            self.logger.debug("Directory path: %s" % path_dir)
        else:
            path_dir = path

        while path_dir.is_symlink():
            path_dir = self._get_build_path(path_dir.resolve())
            self.logger.debug("[%s] Resolved directory symlink: %s" % (path, path_dir))

        if not path_dir.parent.is_dir():
            self.logger.debug("Parent directory does not exist: %s" % path_dir.parent)
            self._mkdir(path_dir.parent, resolve_build=False)

        if not path_dir.is_dir():
            path_dir.mkdir()
            self.logger.log(self["_build_log_level"], "Created directory: %s" % c_(path, "green"))
        else:
            self.logger.debug("Directory already exists: %s" % path_dir)

    def _write(self, file_name: Union[Path, str], contents: list[str], chmod_mask=0o644, append=False) -> None:
        """
        Writes a file within the build directory.
        Sets the passed chmod_mask.
        If the first line is a shebang, sh -n is run on the file.
        """
        file_path = self._get_build_path(file_name)

        if not file_path.parent.is_dir():
            self.logger.debug("Parent directory for '%s' does not exist: %s" % (file_path.name, file_path))
            self._mkdir(file_path.parent, resolve_build=False)

        if isinstance(contents, list):
            contents = "\n".join(contents)

        if file_path.is_file():
            self.logger.warning("File already exists: %s" % c_(file_path, "yellow"))
            if contents in file_path.read_text():
                self.logger.debug("Contents:\n%s" % contents)
                return self.logger.warning("Contents are already present, skipping write: %s" % file_path)

            if self.clean and not append:
                self.logger.warning("Deleting file: %s" % c_(file_path, "red", bright=True, bold=True))
                file_path.unlink()

        self.logger.debug("[%s] Writing contents:\n%s" % (file_path, contents))
        with open(file_path, "a") as file:
            file.write(contents)

        if contents.startswith(self["shebang"].split(" ")[0]):
            self.logger.debug("Running sh -n on file: %s" % file_name)
            try:
                self._run(["sh", "-n", str(file_path)])
            except RuntimeError as e:
                self.logger.error(f"Invalid shell script:\n{pretty_print(contents)}")
                raise ValidationError(f"Failed to validate shell script: {file_name}") from e
        elif contents.startswith("#!"):
            self.logger.warning("[%s] Skipping sh -n on file with unrecognized shebang: %s" % (file_name, contents[0]))

        self.logger.info("Wrote file: %s" % c_(file_path, "green", bright=True))
        file_path.chmod(chmod_mask)
        self.logger.debug("[%s] Set file permissions: %s" % (file_path, chmod_mask))

    def _copy(self, source: Union[Path, str], dest=None) -> None:
        """Copies a file into the initramfs build directory.
        If a destination is not provided, the source is used, under the build directory.

        If the destination parent is a symlink, the symlink is resolved.
        Crates parent directories if they do not exist

        Raises a RuntimeError if the destination path is not within the build directory.
        """
        if not isinstance(source, Path):
            source = Path(source)

        if not dest:
            self.logger.log(5, "No destination specified, using source: %s" % source)
            dest = source

        dest_path = self._get_build_path(dest)
        build_base = self._get_build_path("/")

        while dest_path.parent.is_symlink():
            resolved_path = dest_path.parent.resolve() / dest_path.name
            self.logger.debug("Resolved symlink: %s -> %s" % (dest_path, resolved_path))
            dest_path = self._get_build_path(resolved_path)

        if not dest_path.parent.is_dir():
            self.logger.debug("Parent directory for '%s' does not exist: %s" % (dest_path.name, dest_path.parent))
            self._mkdir(dest_path.parent, resolve_build=False)

        if dest_path.is_file():
            self.logger.warning("File already exists, overwriting: %s" % c_(dest_path, "yellow", bright=True))
        elif dest_path.is_dir():
            self.logger.debug("Destination is a directory, adding source filename: %s" % source.name)
            dest_path = dest_path / source.name

        try:  # Ensure the target is in the build directory
            dest_path.relative_to(build_base)
        except ValueError as e:
            raise RuntimeError("Destination path is not within the build directory: %s" % dest_path) from e

        self.logger.log(self["_build_log_level"], "Copying '%s' to '%s'" % (c_(source, "blue"), c_(dest_path, "green")))
        copy2(source, dest_path)

    def _symlink(self, source: Union[Path, str], target: Union[Path, str]) -> None:
        """Creates a symlink in the build directory.
        If the target is a directory, the source filename is appended to the target path.

        Creates parent directories if they do not exist.
        If the symlink path is under a symlink, resolve to the actual path.

        If the symlink source is under a symlink in the build directory, resolve to the actual path.
        """
        if not isinstance(source, Path):
            source = Path(source)

        target = self._get_build_path(target)

        while target.parent.is_symlink():
            self.logger.debug("Resolving target parent symlink: %s" % target.parent)
            resolved_target = target.parent.resolve() / target.name
            target = self._get_build_path(resolved_target)

        if not target.parent.is_dir():
            self.logger.debug("Parent directory for '%s' does not exist: %s" % (target.name, target.parent))
            self._mkdir(target.parent, resolve_build=False)

        build_source = self._get_build_path(source)
        while build_source.parent.is_symlink():
            self.logger.debug("Resolving source parent symlink: %s" % build_source.parent)
            build_source = self._get_build_path(build_source.parent.resolve() / build_source.name)
            source = build_source.relative_to(self._get_build_path("/"))

        if target.is_symlink():
            if target.resolve() == source:
                return self.logger.debug("Symlink already exists: %s -> %s" % (target, source))
            elif self.clean:
                self.logger.warning("Deleting symlink: %s" % c_(target, "red", bright=True))
                target.unlink()
            else:
                raise RuntimeError("Symlink already exists: %s -> %s" % (target, target.resolve()))

        if target.relative_to(self._get_build_path("/")) == source:
            return self.logger.debug("Cannot symlink to self: %s -> %s" % (target, source))

        self.logger.log(
            self["_build_log_level"], "Creating symlink: %s -> %s" % (c_(target, "green"), c_(source, "blue"))
        )
        target.symlink_to(source)

    def _run(self, args: list[str], timeout=None, fail_silent=False, fail_hard=True) -> CompletedProcess:
        """Runs a command, returns the CompletedProcess object on success.
        If a timeout is set, the command will fail hard if it times out.
        If fail_silent is set, non-zero return codes will not log stderr/stdout.
        If fail_hard is set, non-zero return codes will raise a RuntimeError.
        """

        def print_err(ret) -> None:
            if args := ret.args:
                if isinstance(args, tuple):
                    args = args[0]  # When there's a timeout, args is a (args, timeout) tuple
                self.logger.error("Failed command: %s" % c_(" ".join(args), "red", bright=True))
            if stdout := ret.stdout:
                self.logger.error("Command output:\n%s" % stdout.decode())
            if stderr := ret.stderr:
                self.logger.error("Command error:\n%s" % stderr.decode())

        timeout = timeout or self.timeout
        cmd_args = [str(arg) for arg in args]
        self.logger.debug("Running command: %s" % " ".join(cmd_args))
        try:
            cmd = run(cmd_args, capture_output=True, timeout=timeout)
        except TimeoutExpired as e:
            # Always fail hard for timeouts
            print_err(e)
            raise RuntimeError("[%ds] Command timed out: %s" % (timeout, [str(arg) for arg in cmd_args])) from e

        if cmd.returncode != 0:
            if not fail_silent:
                print_err(cmd)  # Print the full error output if not failing silently
            if fail_hard:  # Fail hard means raise an exception
                raise RuntimeError("Failed to run command: %s" % " ".join(cmd.args))

        return cmd

    def _rotate_old(self, file_name: Path, sequence=0) -> None:
        """Copies a file to file_name.old then file_nane.old.n, where n is the next number in the sequence"""
        # Nothing to do if the file doesn't exist
        if not file_name.is_file():
            self.logger.debug("File does not exist: %s" % file_name)
            return

        # If the cycle count is not set, attempt to clean
        if not self.old_count:
            if self.clean:
                self.logger.warning("Deleting file: %s" % c_(file_name, "red", bold=True, bright=True))
                file_name.unlink()
                return
            else:
                # Fail if the cycle count is not set and clean is disabled
                raise RuntimeError(
                    "Unable to cycle file, as cycle count is not set and clean is disabled: %s" % file_name
                )

        self.logger.debug("[%d] Cycling file: %s" % (sequence, file_name))

        # If the sequence is 0, we're cycling the file for the first time, just rename it to .old
        suffix = ".old" if sequence == 0 else ".old.%d" % sequence
        target_file = file_name.with_suffix(suffix)

        self.logger.debug("[%d] Target file: %s" % (sequence, target_file))
        # If the target file exists, cycle again
        if target_file.is_file():
            # First check if we've reached the cycle limit
            if sequence >= self.old_count:
                # Clean the last file in the sequence if clean is enabled
                if self.clean:
                    self.logger.warning("Deleting old file: %s" % c_(target_file, "red", bold=True, bright=True))
                    target_file.unlink()
                else:
                    self.logger.debug("Cycle limit reached")
                    return
            else:
                self.logger.debug("[%d] Target file exists, cycling again" % sequence)
                self._rotate_old(target_file, sequence + 1)

        # Finally, rename the file
        self.logger.info("[%d] Cycling file: %s -> %s" % (sequence, file_name, target_file))
        file_name.rename(target_file)

    def sort_hook_functions(self, hook: str) -> None:
        """Sorts the functions for the specified hook based on the import order.
        "before" functions are moved before the target function,
        "after" functions' target function is moved before the current function.

        Filters orders which do not contain functions or targets in the current hook.
        """
        func_names = [func.__name__ for func in self["imports"].get(hook, [])]
        if not func_names:
            return self.logger.debug("No functions for hook: %s" % hook)

        b = self["import_order"].get("before", {})
        before = {k: v for k, v in b.items() if k in func_names and any(subv in func_names for subv in b[k])}
        a = self["import_order"].get("after", {})
        after = {k: v for k, v in a.items() if k in func_names and any(subv in func_names for subv in a[k])}

        if not before and not after:
            return self.logger.debug("No import order specified for hook: %s" % hook)

        def iter_order(order, direction):
            """Iterate over all functions in an import order list,
            using this information to move the order of function names in the import list.

            Returns True if any changes were made, False otherwise."""
            changed = False

            for func_name, other_funcs in order.items():
                func_index = func_names.index(func_name)  # Get the index based on the current position
                assert func_index >= 0, "Function not found in import list: %s" % func_name
                for other_func in other_funcs:
                    try:
                        other_index = func_names.index(other_func)
                    except ValueError:
                        continue
                    assert other_index >= 0, "Function not found in import list: %s" % other_func

                    def reorder_func(direction):
                        """Reorders the function based on the direction."""
                        if direction == "before":  # Move the function before the other function
                            self.logger.debug("[%s] Moving function before: %s" % (func_name, other_func))
                            func_names.insert(other_index, func_names.pop(func_index))
                            self["imports"][hook].insert(other_index, self["imports"][hook].pop(func_index))
                        elif direction == "after":  # Move the other function before the current function
                            self.logger.debug("[%s] Moving function before: %s" % (other_func, func_name))
                            func_names.insert(func_index, func_names.pop(other_index))
                            self["imports"][hook].insert(func_index, self["imports"][hook].pop(other_index))
                        else:
                            raise ValueError("Invalid direction: %s" % direction)

                    self.logger.log(5, "[%s] Imports:\n%s", hook, ", ".join(i.__name__ for i in self["imports"][hook]))
                    if direction == "before":  # func_index should be before other_index
                        if func_index > other_index:  # If the current function is after the other function
                            reorder_func("before")  # Move the current function before the other function)
                            changed = True
                        else:  # Log otherwise
                            self.logger.log(5, "Function %s already before: %s" % (func_name, other_func))
                    elif direction == "after":  # func_index should be after other_index
                        if func_index < other_index:  # If the current function is before the other function
                            reorder_func("after")  # Move the current function after the other function
                            changed = True
                        else:
                            self.logger.log(5, "Function %s already after: %s" % (func_name, other_func))
                    else:
                        raise ValueError("Invalid direction: %s" % direction)
                    func_index = func_names.index(func_name)  # Update the index after moving
            return changed

        max_iterations = len(func_names) * (len(before) + 1) * (len(after) + 1)  # Prevent infinite loops
        iterations = max_iterations
        while iterations:
            iterations -= 1
            # Update the order based on the before and after lists
            if not any([iter_order(before, "before"), iter_order(after, "after")]):
                self.logger.debug(
                    "[%s] Import order converged after %s iterations" % (hook, max_iterations - iterations)
                )
                break  # Keep going until no changes are made
        else:  # If the loop completes without breaking, raise an error
            self.logger.error("Import list: %s" % func_names)
            self.logger.error("Before: %s" % before)
            self.logger.error("After: %s" % after)
            raise ValueError("Import order did not converge after %s iterations" % max_iterations)
