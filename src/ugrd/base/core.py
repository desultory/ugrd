__author__ = "desultory"
__version__ = "4.7.3"

from os import environ, makedev, mknod, uname
from pathlib import Path
from shutil import rmtree, which
from stat import S_IFCHR
from subprocess import run
from typing import Union

from ugrd.exceptions import AutodetectError, ValidationError
from zenlib.types import NoDupFlatList
from zenlib.util import colorize as c_
from zenlib.util import contains, unset


def _has_zstd() -> bool:
    from importlib.util import find_spec

    if find_spec("zstandard"):
        return True
    return False


class DecompressorError(Exception):
    """Custom exception for decompressor errors."""

    pass


class LDConfigError(Exception):
    """Custom exception for ldconfig errors."""

    pass


def get_tmpdir(self) -> None:
    """Reads TMPDIR from the environment, sets it as the temporary directory."""
    if tmpdir := environ.get("TMPDIR"):
        self.logger.info("Detected TMPDIR: %s" % (c_(tmpdir, "cyan")))
        self["tmpdir"] = Path(tmpdir)


def _get_shell_path(self, shell_name) -> Path:
    """Gets the real path to the shell binary."""
    if shell := which(shell_name):
        return Path(shell).resolve()
    else:
        raise AutodetectError(f"Shell not found: {shell_name}")


def get_shell(self) -> None:
    """Gets the shell, uses /bin/sh if a shell is not set"""
    if shell := self["shell"]:
        self.logger.info("Using shell: %s", c_(shell, "blue", bright=True))
        self["binaries"] = shell
        shell_path = _get_shell_path(self, shell)
        self["symlinks"]["shell"] = {"target": "/bin/sh", "source": shell_path}
    else:
        self.logger.info("Using default shell: %s", c_("/bin/sh", "cyan"))
        self["binaries"] = "/bin/sh"  # This should pull /bin/sh and the target if it's a symlink


@contains("clean", "Skipping cleaning build directory", log_level=30)
def clean_build_dir(self) -> None:
    """Cleans the build directory.
    Ensures there are no active mounts in the build directory.
    """
    build_dir = self._get_build_path("/")

    if any(mount.startswith(str(build_dir)) for mount in self["_mounts"]):
        self.logger.critical("Mount detected in build directory, stopping: %s" % build_dir)
        self.logger.critical("Active mounts: %s" % self["_mounts"])
        exit(1)

    if build_dir.is_dir():
        self.logger.warning("Cleaning build directory: %s" % c_(build_dir, "yellow"))
        rmtree(build_dir)
    else:
        self.logger.info("Build directory does not exist, skipping cleaning: %s" % build_dir)


def generate_structure(self) -> None:
    """Generates the initramfs directory structure."""
    for subdir in set(self["paths"]):
        self._mkdir(subdir)


def get_conditional_dependencies(self) -> None:
    """Adds conditional dependencies to the dependencies list.
    Keys are the dependency, values are a tuple of the condition type and value.
    """

    def add_dep(dep: str) -> None:
        try:  # Try to add it as a binary, if it fails, add it as a dependency
            self["binaries"] = dep
        except (ValueError, ValidationError):
            self["dependencies"] = dep

    for dependency, condition in self["conditional_dependencies"].items():
        condition_type, condition_value = condition
        match condition_type:
            case "contains":
                contains(condition_value)(add_dep(dependency))
            case "unset":
                unset(condition_value)(add_dep(dependency))


def _determine_interpreter(self, binary: Path) -> str:
    """Checks the shebang of a file, returning the interpreter if it exists."""
    with binary.open("rb") as f:
        try:
            first_line = f.readline().decode("utf-8").strip()
        except UnicodeDecodeError:
            return self.logger.debug(f"Binary is not a text file, skipping shebang check: {c_(binary, 'yellow')}")

        if first_line.startswith("#!"):
            interpreter = first_line[2:].split()[0]
            self.logger.debug(f"[{binary}] Interpreter found: {c_(interpreter, 'green')}")
            return interpreter
        else:
            self.logger.log(5, "No shebang found in: %s" % binary)


def calculate_dependencies(self, binary: str) -> list[Path]:
    """Calculates the dependencies of a binary using lddtree.

    Additionally, pulls the interpreter if defined in the binary's shebang.

    Returns a list of Path objects for each dependency.
    """
    binary_path = which(binary)
    if not binary_path:
        raise AutodetectError(f"Binary not found not found in PATH: {binary}")

    binary_path = Path(binary_path)
    if interpreter := _determine_interpreter(self, binary_path):
        if interpreter not in self["binaries"]:
            self.logger.info(f"[{c_(binary, 'blue')}] Adding interpreter to binaries: {c_(interpreter, 'cyan')}")
            self["binaries"] = interpreter
        else:
            self.logger.debug(f"Interpreter already in binaries list, skipping: {c_(interpreter, 'yellow')}")

    self.logger.debug("Calculating dependencies for: %s" % binary_path)
    dependencies = run(["lddtree", "-l", str(binary_path)], capture_output=True)

    if dependencies.returncode != 0:
        self.logger.warning("Unable to calculate dependencies for: %s" % c_(binary, "red", bold=True, bright=True))
        raise AutodetectError("Unable to resolve dependencies, error: %s" % dependencies.stderr.decode("utf-8"))

    dependency_paths = []
    for dependency in dependencies.stdout.decode("utf-8").splitlines():
        # Remove extra slash at the start if it exists
        if dependency.startswith("//"):
            dependency = dependency[1:]

        dependency_paths.append(Path(dependency))
    self.logger.debug("[%s] Calculated dependencies: %s" % (binary, dependency_paths))
    return dependency_paths


def find_library(self, library: str) -> None:
    """Given a library file name, searches for it in the library paths, adds it to the dependencies list."""
    search_paths = NoDupFlatList(self["library_paths"], logger=self.logger)
    search_paths.append(["/lib64", "/lib", "/usr/lib64", "/usr/lib"])

    for path in search_paths:
        lib_path = Path(path).joinpath(library)
        if lib_path.exists():
            self.logger.info(f"[{c_(library, 'blue')}] Found library file: {c_(lib_path, 'cyan')}")
            return lib_path
        # Attempt to find the library with a .so extension
        lib_path = lib_path.with_suffix(".so")
        if lib_path.exists():
            self.logger.info(f"[{c_(library, 'blue')}] Found library file: {c_(lib_path, 'cyan')}")
            return lib_path
    raise AutodetectError("Library not found: %s" % library)


@contains("merge_usr", "Skipping /usr merge", log_level=30)
def handle_usr_symlinks(self) -> None:
    """
    Adds symlinks for /bin and /sbin to /usr/bin
    Adds a symlink for /usr/sbin to /usr/bin (-> bin)
    Adds smlinks for /lib to /usr/lib and /lib64 to /usr/lib64
    Warns if the symlink path is a directory on the host system.
    """
    bin_symlink = ("bin", "usr/bin")
    sbin_symlink = ("sbin", "usr/bin")
    usr_sbin_symlink = ("usr/sbin", "bin")  # Make it relative
    lib_symlink = ("lib", "usr/lib")
    lib64_symlink = ("lib64", "usr/lib64")
    symlinks = [bin_symlink, sbin_symlink, usr_sbin_symlink, lib_symlink, lib64_symlink]

    for target, source in symlinks:
        host_path = Path("/").joinpath(target)
        if host_path.is_dir() and not host_path.is_symlink():
            self.logger.warning("Host path is a directory, skipping symlink creation: %s" % host_path)
            self.logger.warning("Set `merge_usr = false` to disable /usr merge.")
            continue
        self._symlink(source, target)


def deploy_dependencies(self) -> None:
    """Copies all dependencies to the build directory."""
    for dependency in self["dependencies"]:
        if dependency.is_symlink():
            if self["symlinks"].get(f"_auto_{dependency.name}"):
                self.logger.debug("Dependency is a symlink, skipping: %s" % dependency)
                continue
            else:
                raise ValueError("Dependency is a symlink and not in the symlinks list: %s" % dependency)

        self._copy(dependency)


def _deploy_compressed(self, compression_type: str, decompressor, compression_extensions=None) -> None:
    """Decompresses all dependencies of the specified compression type into the build directory.
    Remove the compression extension if there is a match between compression_extensions and the file name.
    """
    compression_extensions = compression_extensions or [f".{compression_type}"]

    for dependency in self[f"{compression_type}_dependencies"]:
        self.logger.debug(f"[{compression_type}] Decompressing: {dependency}")

        for extension in compression_extensions:
            if str(dependency).endswith(extension):
                break
        else:
            self.logger.warning(f"[{compression_type}] Dependency missing extension: {dependency}")
            extension = ""

        self.logger.debug(f"[{compression_type}] Found compressed file: {dependency}")
        # Replace the extension, do nothing if there is no match
        out_path = self._get_build_path(str(dependency).replace(extension, ""))
        if not out_path.parent.is_dir():
            self.logger.debug(f"Creating parent directory: {out_path.parent}")
            self._mkdir(out_path.parent, resolve_build=False)

        try:
            data = decompressor(dependency.read_bytes())
        except Exception as e:
            raise DecompressorError(f"[{compression_type}] Unable to decompress ependency: {dependency} ({e})")

        with out_path.open("wb") as out_file:
            out_file.write(data)
            self.logger.info(
                f"[{c_(compression_type, 'green', bright=True)}] Decompressed {c_(dependency, 'blue')} -> {c_(out_path, 'green')}"
            )


@contains("xz_dependencies", "No xz dependencies defined, skipping.", log_level=10)
def deploy_xz_dependencies(self) -> None:
    """Decompresses all xz dependencies into the build directory."""
    from lzma import decompress

    _deploy_compressed(self, "xz", decompress)


@contains("zstd_dependencies", "No zstd dependencies defined, skipping.", log_level=10)
def deploy_zstd_dependencies(self) -> None:
    """Decompresses all zstd dependencies into the build directory.
    Entries should only be added to zstd_dependencies if the zstandard library is available.
    """
    from zstandard import decompress

    _deploy_compressed(self, "zstd", decompress, compression_extensions=[".zst", ".zstd"])


@contains("gz_dependencies", "No gz dependencies defined, skipping.", log_level=10)
def deploy_gz_dependencies(self) -> None:
    """Decompresses all gzip dependencies into the build directory."""
    from gzip import decompress

    _deploy_compressed(self, "gz", decompress)


def deploy_copies(self) -> None:
    """Copies everything from self['copies'] into the build directory."""
    for copy_name, copy_parameters in self["copies"].items():
        self.logger.debug("[%s] Copying: %s" % (copy_name, copy_parameters))
        self._copy(copy_parameters["source"], copy_parameters["destination"])


def deploy_symlinks(self) -> None:
    """Creates symlinks for all symlinks in self['symlinks']."""
    for symlink_name, symlink_parameters in self["symlinks"].items():
        self.logger.debug("[%s] Creating symlink: %s" % (symlink_name, symlink_parameters))
        self._symlink(symlink_parameters["source"], symlink_parameters["target"])


@contains("nodes", "Skipping device node creation, no nodes are defined.")
@contains("make_nodes", "Skipping real device node creation with mknod, as make_nodes is not specified.", log_level=20)
def deploy_nodes(self) -> None:
    """Generates specified device nodes."""
    for node, config in self["nodes"].items():
        node_path_abs = Path(config["path"])

        node_path = self._get_build_path("/") / node_path_abs.relative_to(node_path_abs.anchor)
        node_mode = S_IFCHR | config["mode"]

        try:
            mknod(node_path, mode=node_mode, device=makedev(config["major"], config["minor"]))
            self.logger.info("Created device node '%s' at path: %s" % (node, node_path))
        except PermissionError as e:
            self.logger.error("Unable to create device node %s at path: %s" % (node, node_path))
            self.logger.info(
                "When `make_nodes` is disabled, device nodes are synthetically created in the resulting CPIO archive."
            )
            raise e


def _get_ldconfig(self) -> list:
    """Returns the ldconfig command if it exists, otherwise raise an LDConfigError."""
    try:
        cmd = self._run(["ldconfig", "-p"], fail_silent=True, fail_hard=False)
    except FileNotFoundError:
        self.logger.warning("If musl libc is being used, `musl_libc = true` should be set in the config.")
        raise LDConfigError("ldconfig not found, unable to resolve libraries.")

    if b"Unimplemented option: -p" in cmd.stderr:  # Probably musl libc
        self.logger.warning("If musl libc is being used, `musl_libc = true` should be set in the config.")
        raise LDConfigError("ldconfig -p not supported, musl libc is likely in use.")

    if cmd.returncode != 0:
        raise LDConfigError("ldconfig failed to run: %s" % cmd.stderr.decode("utf-8"))

    self.logger.log(5, "ldconfig -p output:\n%s" % cmd.stdout.decode())
    return cmd.stdout.decode().splitlines()


@unset("musl_libc", "Skipping libgcc_s dependency resolution, musl_libc is enabled.", log_level=20)
@contains("find_libgcc", "Skipping libgcc_s dependency resolution", log_level=20)
def autodetect_libgcc(self) -> None:
    """Finds libgcc.so, adds a 'dependencies' item for it.
    Adds the parent directory to 'library_paths'
    """
    try:
        ldconfig = _get_ldconfig(self)
    except LDConfigError:
        self.logger.warning("Unable to run ldconfig -p, if glibc is being used, this is fatal!")
        self.logger.warning("If libgcc_s is not required, set `find_libgcc = false` in the configuration.")
        return

    libgcc_libs = [lib for lib in ldconfig if "libgcc_s" in lib]
    if not libgcc_libs:
        raise AutodetectError("libgcc_s not found in ldconfig output")

    # Find the best match for libgcc_s
    for lib in libgcc_libs:
        # Prefer the multiarch version if it exists
        if "(libc6," in lib:
            libgcc = lib
            break
        # Otherwise use the 32 bit version if it exists
        elif "(libc6)" in lib:
            libgcc = lib
            self.logger.warning("Using 32-bit libgcc_s version, multiarch version not found.")
            break
    else:
        raise AutodetectError("No suitable libgcc_s version found in ldconfig output")

    source_path = Path(libgcc.partition("=> ")[-1])
    self.logger.info(f"Source path for libgcc_s: {c_(source_path, 'green')}")

    self["dependencies"] = source_path
    self["library_paths"] = str(source_path.parent)


def autodetect_musl(self) -> None:
    """Looks for /etc/ld-musl-<arch>.path
    If it exists, adds it to the dependencies list.
    """
    arch = uname().machine
    musl_path = Path(f"/etc/ld-musl-{arch}.path")
    if musl_path.exists():
        self.logger.info(f"Detected musl search path: {c_(musl_path, 'green')}")
        self["dependencies"] = musl_path
    elif self["musl_libc"]:
        raise AutodetectError("Musl libc is enabled, but the musl search path was not found: %s" % musl_path)


@unset("musl_libc", "Skipping ld.so.cache regeneration, musl_libc is enabled.", log_level=30)
def regen_ld_so_cache(self) -> None:
    """
    Checks if a 'real' ldconfig is available, if so, regenerates the ld.so.cache file in the build dir.
    Uses defined library paths to generate the config file.

    If ldconfig is not available, _get_ldconfiig will warn about setting `musl_libc` to true.
    Here, warn about this and that this is a fatal error if glibc is being used.
    """
    try:
        _get_ldconfig(self)
    except LDConfigError:
        return self.logger.warning("Unable to run ldconfig -p, if glibc is being used, this is fatal!")

    self.logger.info("Regenerating ld.so.cache")
    self._write("etc/ld.so.conf", self["library_paths"])
    build_path = self._get_build_path("/")
    self._run(["ldconfig", "-r", str(build_path)])
    self["check_included_or_mounted"] = "etc/ld.so.cache"


def _process_out_file(self, out_file: str) -> None:
    """Processes the out_file.

    If set to the current directory, resolves and sets the out_dir to the current directory.
    If a '/' is present, resolves the path and sets the out_dir to the parent directory.
    If out_file is a directory, sets the out_dir to the directory, stops processing.
    """
    out_file = str(out_file)
    if out_file == "./" or out_file == ".":
        current_dir = Path(".").resolve()
        self.logger.info("Setting out_dir to current directory: %s" % c_(current_dir, "cyan", bold=True))
        self["out_dir"] = current_dir
        return

    if "/" in out_file:  # If the out_file contains a path, resolve it
        out_file = Path(out_file)
        resolved_out_file = out_file.resolve()
        if resolved_out_file != out_file:
            out_file = resolved_out_file
            self.logger.info("Resolved relative output path: %s" % out_file)
    else:
        out_file = Path(out_file)

    if out_file.is_dir():
        self.logger.info("Specified out_file is a directory, setting out_dir: %s" % out_file)
        self["out_dir"] = out_file
        return

    if str(out_file.parent) != ".":  # If the parent isn't the curent dir, set the out_dir to the parent
        self["out_dir"] = out_file.parent
        self.logger.info("Resolved out_dir to: %s" % c_(self["out_dir"], "green"))
        out_file = out_file.name

    self.data["out_file"] = out_file


def _process_paths_multi(self, path: Union[Path, str]) -> None:
    """Processes a path entry.
    Converts the input to a Path if it is not one.
    Checks if the path is absolute, and if so, converts it to a relative path.
    """
    self.logger.log(5, "Processing path: %s" % path)
    if not isinstance(path, Path):
        path = Path(path)

    # Make sure the path is relative
    if path.is_absolute():
        path = path.relative_to(path.anchor)
        self.logger.debug("Path was absolute, converted to relative: %s" % path)

    self.logger.debug("Adding path: %s" % path)
    self["paths"].append(path)


def _process_libraries_multi(self, library: Union[str]) -> None:
    """Prociesses libraries into the libraries list, adding the parent directory to the library paths."""
    if library in self["libraries"]:
        return self.logger.debug("Library already in libraries list, skipping: %s" % library)

    self.logger.debug("Processing library: %s" % library)
    library_path = find_library(self, library)
    self["libraries"].append(library)
    self["dependencies"] = library_path
    self["library_paths"] = str(library_path.parent)


def _process_binaries_multi(self, binary: str) -> None:
    """Processes binaries into the binaries list, adding dependencies along the way."""
    if binary in self["binaries"]:
        return self.logger.debug("Binary already in binaries list, skipping: %s" % binary)

    # Check if there is an import function that collides with the name of the binary
    if funcs := self["imports"].get("functions"):
        if binary in funcs:
            raise ValueError("Binary name collides with import function name: %s" % binary)

    self.logger.debug("Processing binary: %s" % binary)

    dependencies = calculate_dependencies(self, binary)
    # The first dependency will be the path of the binary itself, don't add this to the library paths
    self["dependencies"] = dependencies[0]
    for dependency in dependencies[1:]:
        self.logger.debug("[%s] Adding dependency: %s" % (binary, dependency))
        self["dependencies"] = dependency
        if str(dependency.parent) not in self["library_paths"]:
            self.logger.info("Adding library path: %s" % dependency.parent)
            # Make it a string so NoDupFlatList can handle it
            # It being derived from a path should ensure it's a proper path
            self["library_paths"] = str(dependency.parent)

    self.logger.debug("Adding binary: %s" % binary)
    self["binaries"].append(binary)
    self["binary_search_paths"] = str(dependencies[0].parent)  # Add the binary path to the search paths


def _validate_dependency(self, dependency: Union[Path, str]) -> Path:
    """Performas basic validation and normalization for dependencies.
    Returns the dependency as a Path object.
    Raises a ValidationError if the dependency path does not exist.
    """
    if not isinstance(dependency, Path):
        dependency = Path(dependency)

    if not dependency.exists():
        raise ValidationError("Dependency does not exist: %s" % dependency)

    return dependency


def _process_dependencies_multi(self, dependency: Union[Path, str]) -> None:
    """Processes dependencies.
    Converts the input to a Path if it is not one, checks if it exists.
    If the dependency is a symlink, resolve it and add it to the symlinks list."""
    dependency = _validate_dependency(self, dependency)

    if dependency.is_dir():
        self.logger.debug("Dependency is a directory, adding to paths: %s" % dependency)
        self["paths"] = dependency
        return

    while dependency.is_symlink():
        if self["symlinks"].get(f"_auto_{dependency.name}"):
            self.logger.log(
                5, "Dependency is a symlink which is already in the symlinks list, skipping: %s" % dependency
            )
            break
        else:
            resolved_path = dependency.resolve()
            self.logger.debug("Dependency is a symlink, adding to symlinks: %s -> %s" % (dependency, resolved_path))
            self["symlinks"][f"_auto_{dependency.name}"] = {"source": resolved_path, "target": dependency}
            dependency = resolved_path

    if dependency.is_symlink():
        dependency = dependency.resolve()
        self.logger.debug("Dependency target is a symlink, resolved to: %s" % dependency)

    self.logger.debug("Added dependency: %s" % dependency)
    self["dependencies"].append(dependency)


def _process_opt_dependencies_multi(self, dependency: Union[Path, str]) -> None:
    """Processes optional dependencies."""
    try:
        _process_dependencies_multi(self, dependency)
    except FileNotFoundError as e:
        self.logger.warning("Optional dependency not found, skipping: %s" % dependency)
        self.logger.debug(e)


def _process_xz_dependencies_multi(self, dependency: Union[Path, str]) -> None:
    """Processes xz dependencies.
    Checks that the file is a xz file, and adds it to the xz dependencies list.
    !! Resolves symlinks implicitly !!
    """
    dependency = _validate_dependency(self, dependency)
    if dependency.suffix != ".xz":
        self.logger.warning("XZ dependency missing xz extension: %s" % dependency)
    self["xz_dependencies"].append(dependency)


def _process_gz_dependencies_multi(self, dependency: Union[Path, str]) -> None:
    """Processes gzip dependencies.
    Checks that the file is a gz file, and adds it to the gz dependencies list.
    !! Resolves symlinks implicitly !!
    """
    dependency = _validate_dependency(self, dependency)
    if dependency.suffix != ".gz":
        self.logger.warning("GZIP dependency missing gz extension: %s" % dependency)
    self["gz_dependencies"].append(dependency)


def _process_zstd_dependencies_multi(self, dependency: Union[Path, str]) -> None:
    """Processes zstd dependencies.
    Checks that the file is a zst file, and adds it to the zstd dependencies list.
    Adds the dependency to 'dependencies' if the zstandard library is not found.
    !! Resolves symlinks implicitly !!
    """
    if not _has_zstd():
        self["dependencies"] = dependency
        return self.logger.warning(
            f"Python zstandard library not found, adding to dependencies: {c_(dependency, 'yellow', bold=True)}"
        )

    dependency = _validate_dependency(self, dependency)
    if dependency.suffix != ".zst":
        self.logger.warning("ZSTD dependency missing zst extension: %s" % dependency)
    self["zstd_dependencies"].append(dependency)


def _process_build_logging(self, log_build: bool) -> None:
    """Sets the build log flag."""
    build_log_level = self.get("_build_log_level", 10)
    if log_build == self["build_logging"]:
        # Don't re-run the setup procedure as it will bump the log level again when args are re-processed
        return self.logger.debug("Build logging is already set to: %s" % log_build)
    if log_build:
        self["_build_log_level"] = max(build_log_level + 10, 20)
    else:
        if self["_build_log_level"] > 10:
            self.logger.warning("Resetting _build_log_level to 10, as build logging is disabled.")
            self["_build_log_level"] = 10
    self.data["build_logging"] = log_build


def _process_copies_multi(self, name: str, parameters: dict) -> None:
    """Processes a copy from the copies parameter. Ensures the source and target are defined in the parameters."""
    self.logger.log(5, "[%s] Processing copies: %s" % (name, parameters))
    if "source" not in parameters:
        raise ValueError("[%s] No source specified" % name)
    if "destination" not in parameters:
        raise ValueError("[%s] No destination specified" % name)

    self.logger.debug("[%s] Adding copies: %s" % (name, parameters))
    self["copies"][name] = parameters


def _process_symlinks_multi(self, name: str, parameters: dict) -> None:
    """Processes a symlink. Ensures the source and target are defined in the parameters."""
    self.logger.log(5, "[%s] Processing symlink: %s" % (name, parameters))
    if "source" not in parameters:
        raise ValueError("[%s] No source specified" % name)
    if "target" not in parameters:
        raise ValueError("[%s] No target specified" % name)

    self.logger.debug("[%s] Adding symlink: %s -> %s" % (name, parameters["source"], parameters["target"]))
    self["symlinks"][name] = parameters


def _process_nodes_multi(self, name: str, config: dict) -> None:
    """Process a device node. Ensures the major and minor are defined in the parameters."""
    if "major" not in config:
        raise ValueError("[%s] No major specified" % name)
    if "minor" not in config:
        raise ValueError("[%s] No minor specified" % name)

    if "path" not in config:
        config["path"] = f"dev/{name}"
        self.logger.debug("[%s] No path specified, assuming: %s" % (name, config["path"]))

    if "mode" not in config:
        config["mode"] = 0o660
        self.logger.debug("[%s] No mode specified, assuming: %s" % (name, config["mode"]))

    self.logger.debug("[%s] Adding node: %s" % (name, config))
    self["nodes"][name] = config


def _process_masks_multi(self, runlevel: str, function: str) -> None:
    """Processes a mask definition. Masks are used to prevent functions from being run at a specific runlevel."""
    if runlevel not in self["masks"]:
        self.logger.debug("Creating new mask: %s" % runlevel)
        self["masks"][runlevel] = NoDupFlatList(logger=self.logger)
    self.logger.info("[%s] Adding mask: %s" % (runlevel, c_(function, "red")))
    self["masks"][runlevel] = function


def _process_hostonly(self, hostonly: bool) -> None:
    """Processes the hostonly parameter.
    If validation is enabled, and hostonly mode is set to disabled, disable validation and warn."""
    self.logger.debug("Processing hostonly: %s" % hostonly)
    self.data["hostonly"] = hostonly
    if not hostonly and self["validate"]:
        self.logger.warning("Hostonly is disabled, disabling validation")
        self["validate"] = False


def _process_validate(self, validate: bool) -> None:
    """Processes the validate parameter.
    Only allowed if hostonly mode is enabled."""
    self.logger.debug("Processing validate: %s" % validate)
    if not self["hostonly"] and validate:
        raise ValueError("Cannot enable validation when hostonly mode is disabled")
    self.data["validate"] = validate
