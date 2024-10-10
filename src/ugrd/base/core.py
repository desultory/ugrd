__author__ = 'desultory'
__version__ = '3.8.0'

from pathlib import Path
from typing import Union

from zenlib.util import contains, unset, NoDupFlatList


def detect_tmpdir(self) -> None:
    """ Reads TMPDIR from the environment, sets it as the temporary directory. """
    from os import environ
    if tmpdir := environ.get('TMPDIR'):
        self.logger.info("Detected TMPDIR: %s" % tmpdir)
        self['tmpdir'] = Path(tmpdir)


@contains('clean', "Skipping cleaning build directory", log_level=30)
def clean_build_dir(self) -> None:
    """ Cleans the build directory. """
    from shutil import rmtree

    build_dir = self._get_build_path('/')

    if build_dir.is_dir():
        self.logger.warning("Cleaning build directory: %s" % build_dir)
        rmtree(build_dir)
    else:
        self.logger.info("Build directory does not exist, skipping cleaning: %s" % build_dir)


def generate_structure(self) -> None:
    """ Generates the initramfs directory structure. """
    for subdir in set(self['paths']):
        self._mkdir(subdir)


def calculate_dependencies(self, binary: str) -> list[Path]:
    """
    Calculates the dependencies of a binary using lddtree
    :param binary: The binary to calculate dependencies for
    """
    from shutil import which
    from subprocess import run

    binary_path = which(binary)
    if not binary_path:
        raise RuntimeError("'%s' not found in PATH" % binary)

    binary_path = Path(binary_path)

    self.logger.debug("Calculating dependencies for: %s" % binary_path)
    dependencies = run(['lddtree', '-l', str(binary_path)], capture_output=True)

    if dependencies.returncode != 0:
        self.logger.warning("Unable to calculate dependencies for: %s" % binary)
        raise RuntimeError("Unable to resolve dependencies, error: %s" % dependencies.stderr.decode('utf-8'))

    dependency_paths = []
    for dependency in dependencies.stdout.decode('utf-8').splitlines():
        # Remove extra slash at the start if it exists
        if dependency.startswith('//'):
            dependency = dependency[1:]

        dependency_paths.append(Path(dependency))

    return dependency_paths


def handle_usr_symlinks(self) -> None:
    """ Adds symlinks for /usr/bin and /usr/sbin to /bin and /sbin. """
    build_dir = self._get_build_path('/')

    if not (build_dir / 'bin').is_dir():
        if (build_dir / 'usr/bin').is_dir():
            self._symlink('/usr/bin', '/bin/')
        else:
            raise RuntimeError("Neither /bin nor /usr/bin exist in the build directory")

    if not (build_dir / 'sbin').is_dir() and (build_dir / 'usr/sbin').is_dir():
        self._symlink('/usr/sbin', '/sbin/')


def deploy_dependencies(self) -> None:
    """ Copies all dependencies to the build directory. """
    for dependency in self['dependencies']:
        if dependency.is_symlink():
            if self['symlinks'].get(f'_auto_{dependency.name}'):
                self.logger.debug("Dependency is a symlink, skipping: %s" % dependency)
                continue
            else:
                raise ValueError("Dependency is a symlink and not in the symlinks list: %s" % dependency)

        self._copy(dependency)


def deploy_xz_dependencies(self) -> None:
    """ Decompresses all xz dependencies into the build directory. """
    from lzma import decompress
    for xz_dependency in self['xz_dependencies']:
        self.logger.debug("[xz] Decompressing: %s" % xz_dependency)
        out_path = self._get_build_path(str(xz_dependency).replace('.xz', ''))
        if not out_path.parent.is_dir():
            self.logger.debug("Creating parent directory: %s" % out_path.parent)
            self._mkdir(out_path.parent, resolve_build=False)
        with out_path.open('wb') as out_file:
            out_file.write(decompress(xz_dependency.read_bytes()))
            self.logger.info("[xz] Decompressed '%s' to: %s" % (xz_dependency, out_path))


def deploy_gz_dependencies(self) -> None:
    """ Decompresses all gzip dependencies into the build directory. """
    from gzip import decompress
    for gz_dependency in self['gz_dependencies']:
        self.logger.debug("[gz] Decompressing: %s" % gz_dependency)
        out_path = self._get_build_path(str(gz_dependency).replace('.gz', ''))
        if not out_path.parent.is_dir():
            self.logger.debug("Creating parent directory: %s" % out_path.parent)
            self._mkdir(out_path.parent, resolve_build=False)
        with out_path.open('wb') as out_file:
            out_file.write(decompress(gz_dependency.read_bytes()))
            self.logger.info("[gz] Decompressed '%s' to: %s" % (gz_dependency, out_path))


def deploy_copies(self) -> None:
    """ Copies everything from self['copies'] into the build directory. """
    for copy_name, copy_parameters in self['copies'].items():
        self.logger.debug("[%s] Copying: %s" % (copy_name, copy_parameters))
        self._copy(copy_parameters['source'], copy_parameters['destination'])


def deploy_symlinks(self) -> None:
    """ Creates symlinks for all symlinks in self['symlinks']."""
    for symlink_name, symlink_parameters in self['symlinks'].items():
        self.logger.debug("[%s] Creating symlink: %s" % (symlink_name, symlink_parameters))
        self._symlink(symlink_parameters['source'], symlink_parameters['target'])


@unset('mknod_cpio', "Skipping real device node creation with mknod, as mknod_cpio is not specified.", log_level=20)
def deploy_nodes(self) -> None:
    """ Generates specified device nodes. """
    from os import makedev, mknod
    from stat import S_IFCHR

    for node, config in self['nodes'].items():
        node_path_abs = Path(config['path'])

        node_path = self._get_build_path('/') / node_path_abs.relative_to(node_path_abs.anchor)
        node_mode = S_IFCHR | config['mode']

        try:
            mknod(node_path, mode=node_mode, device=makedev(config['major'], config['minor']))
            self.logger.info("Created device node '%s' at path: %s" % (node, node_path))
        except PermissionError as e:
            self.logger.error("Unable to create device node %s at path: %s" % (node, node_path))
            self.logger.info("`mknod_cpio` in `ugrd.base` can be used to generate device nodes within the initramfs archive if they cannot be created on the host system.")
            raise e


@contains('find_libgcc', "Skipping libgcc_s dependency resolution", log_level=20)
def find_libgcc(self) -> None:
    """
    Finds libgcc.so, adds a 'dependencies' item for it.
    Adds the parent directory to 'library_paths'
    """
    from pathlib import Path

    try:
        ldconfig = self._run(['ldconfig', '-p']).stdout.decode().split("\n")
    except RuntimeError:
        return self.logger.critical("Unable to run ldconfig -p, if GCC is being used, this is fatal!")

    libgcc = [lib for lib in ldconfig if 'libgcc_s' in lib and '(libc6,' in lib][0]
    source_path = Path(libgcc.partition('=> ')[-1])
    self.logger.info("Source path for libgcc_s: %s" % source_path)

    self['dependencies'] = source_path
    self['library_paths'] = str(source_path.parent)


def _process_out_file(self, out_file):
    """ Processes the out_file configuration option. """
    if Path(out_file).is_dir():
        self.logger.info("Specified out_file is a directory, setting out_dir: %s" % out_file)
        self['out_dir'] = out_file
        return

    if out_file.startswith('./'):
        self.logger.debug("Relative out_file path detected: %s" % out_file)
        self['out_dir'] = Path('.').resolve()
        self.logger.info("Resolved out_dir to: %s" % self['out_dir'])
        out_file = Path(out_file[2:])
    elif Path(out_file).parent.is_dir() and str(Path(out_file).parent) != '.':
        self['out_dir'] = Path(out_file).parent
        self.logger.info("Resolved out_dir to: %s" % self['out_dir'])
        out_file = Path(out_file).name
    else:
        out_file = Path(out_file)

    self.data['out_file'] = out_file


def _process_paths_multi(self, path: Union[Path, str]) -> None:
    """
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
    self['paths'].append(path)


def _process_binaries_multi(self, binary: str) -> None:
    """ Processes binaries into the binaries list, adding dependencies along the way. """
    if binary in self['binaries']:
        return self.logger.debug("Binary already in binaries list, skipping: %s" % binary)

    # Check if there is an import function that collides with the name of the binary
    if funcs := self['imports'].get('functions'):
        if binary in funcs:
            raise ValueError("Binary name collides with import function name: %s" % binary)

    self.logger.debug("Processing binary: %s" % binary)

    dependencies = calculate_dependencies(self, binary)
    # The first dependency will be the path of the binary itself, don't add this to the library paths
    self['dependencies'] = dependencies[0]
    for dependency in dependencies[1:]:
        self['dependencies'] = dependency
        if str(dependency.parent) not in self['library_paths']:
            self.logger.info("Adding library path: %s" % dependency.parent)
            # Make it a string so NoDupFlatList can handle it
            # It being derived from a path should ensure it's a proper path
            self['library_paths'] = str(dependency.parent)

    self.logger.debug("Adding binary: %s" % binary)
    self['binaries'].append(binary)


def _validate_dependency(self, dependency: Union[Path, str]) -> None:
    """ Performas basic validation and normalization for dependencies. """
    if not isinstance(dependency, Path):
        dependency = Path(dependency)

    if not dependency.exists():
        raise FileNotFoundError("Dependency does not exist: %s" % dependency)

    return dependency


def _process_dependencies_multi(self, dependency: Union[Path, str]) -> None:
    """
    Converts the input to a Path if it is not one, checks if it exists.
    If the dependency is a symlink, resolve it and add it to the symlinks list.
    """
    dependency = _validate_dependency(self, dependency)

    if dependency.is_symlink():
        if self['symlinks'].get(f'_auto_{dependency.name}'):
            self.logger.log(5, "Dependency is a symlink which is already in the symlinks list, skipping: %s" % dependency)
        else:
            resolved_path = dependency.resolve()
            self.logger.debug("Dependency is a symlink, adding to symlinks: %s -> %s" % (dependency, resolved_path))
            self['symlinks'][f'_auto_{dependency.name}'] = {'source': resolved_path, 'target': dependency}
            dependency = resolved_path

    self.logger.debug("Added dependency: %s" % dependency)
    self['dependencies'].append(dependency)


def _process_opt_dependencies_multi(self, dependency: Union[Path, str]) -> None:
    """ Processes optional dependencies. """
    try:
        _process_dependencies_multi(self, dependency)
    except FileNotFoundError as e:
        self.logger.warning("Optional dependency not found, skipping: %s" % dependency)
        self.logger.debug(e)


def _process_xz_dependencies_multi(self, dependency: Union[Path, str]) -> None:
    """
    Checks that the file is a xz file, and adds it to the xz dependencies list.
    !! Resolves symlinks implicitly !!
    """
    dependency = _validate_dependency(self, dependency)
    if dependency.suffix != '.xz':
        self.logger.warning("XZ dependency missing xz extension: %s" % dependency)
    self['xz_dependencies'].append(dependency)


def _process_gz_dependencies_multi(self, dependency: Union[Path, str]) -> None:
    """
    Checks that the file is a gz file, and adds it to the gz dependencies list.
    !! Resolves symlinks implicitly !!
    """
    dependency = _validate_dependency(self, dependency)
    if dependency.suffix != '.gz':
        self.logger.warning("GZIP dependency missing gz extension: %s" % dependency)
    self['gz_dependencies'].append(dependency)


def _process_build_logging(self, log_build: bool) -> None:
    """ Sets the build log flag. """
    build_log_level = self.get('_build_log_level', 10)
    if log_build:
        self['_build_log_level'] = max(build_log_level + 10, 20)
    else:
        if self['_build_log_level'] > 10:
            self.logger.warning("Resetting _build_log_level to 10, as build logging is disabled.")
        self['_build_log_level'] = 10
    self.data['build_logging'] = log_build


def _process_copies_multi(self, name: str, parameters: dict) -> None:
    """
    Processes a copy from the copies parameter
    Ensures the source and target are defined in the parameters.
    """
    self.logger.log(5, "[%s] Processing copies: %s" % (name, parameters))
    if 'source' not in parameters:
        raise ValueError("[%s] No source specified" % name)
    if 'destination' not in parameters:
        raise ValueError("[%s] No target specified" % name)

    self.logger.debug("[%s] Adding copies: %s" % (name, parameters))
    self['copies'][name] = parameters


def _process_symlinks_multi(self, name: str, parameters: dict) -> None:
    """
    Processes a symlink,
    Ensures the source and target are defined in the parameters.
    """
    self.logger.log(5, "[%s] Processing symlink: %s" % (name, parameters))
    if 'source' not in parameters:
        raise ValueError("[%s] No source specified" % name)
    if 'target' not in parameters:
        raise ValueError("[%s] No target specified" % name)

    self.logger.debug("[%s] Adding symlink: %s -> %s" % (name, parameters['source'], parameters['target']))
    self['symlinks'][name] = parameters


def _process_nodes_multi(self, name: str, config: dict) -> None:
    """
    Process a device node.
    Validates the major and minor are defined in the parameters.
    """
    if 'major' not in config:
        raise ValueError("[%s] No major specified" % name)
    if 'minor' not in config:
        raise ValueError("[%s] No minor specified" % name)

    if 'path' not in config:
        config['path'] = f"dev/{name}"
        self.logger.debug("[%s] No path specified, assuming: %s" % (name, config['path']))

    if 'mode' not in config:
        config['mode'] = 0o660
        self.logger.debug("[%s] No mode specified, assuming: %s" % (name, config['mode']))

    self.logger.debug("[%s] Adding node: %s" % (name, config))
    self['nodes'][name] = config


def _process_masks_multi(self, runlevel: str, function: str) -> None:
    """ Processes a mask definition. """
    if runlevel not in self['masks']:
        self.logger.debug("Creating new mask: %s" % runlevel)
        self['masks'][runlevel] = NoDupFlatList(looggger=self.logger, _log_init=False)
    self.logger.info("[%s] Adding mask: %s" % (runlevel, function))
    self['masks'][runlevel] = function


def _process_hostonly(self, hostonly: bool) -> None:
    """
    Processes the hostonly parameter.
    If validation is enabled, and hostonly mode is set to disabled, disable validation and warn.
    """
    self.logger.debug("Processing hostonly: %s" % hostonly)
    self.data['hostonly'] = hostonly
    if not hostonly and self['validate']:
        self.logger.warning("Hostonly is disabled, disabling validation")
        self['validate'] = False


def _process_validate(self, validate: bool) -> None:
    """
    Processes the validate parameter.
    It should only be allowed if hostonly mode is enabled.
    """
    self.logger.debug("Processing validate: %s" % validate)
    if not self['hostonly'] and validate:
        raise ValueError("Cannot enable validation when hostonly mode is disabled")
    self.data['validate'] = validate

