__author__ = 'desultory'
__version__ = '2.3.1'

from pathlib import Path
from typing import Union


def clean_build_dir(self) -> None:
    """ Cleans the build directory. """
    from shutil import rmtree

    if not self.clean:
        self.logger.info("Skipping cleaning build directory")
        return

    if self.build_dir.is_dir():
        self.logger.warning("Cleaning build directory: %s" % self.build_dir)
        rmtree(self.build_dir)
    else:
        self.logger.info("Build directory does not exist, skipping cleaningi: %s" % self.build_dir)


def generate_structure(self) -> None:
    """ Generates the initramfs directory structure. """
    if not self.build_dir.is_dir():
        self._mkdir(self.build_dir)

    for subdir in set(self['paths']):
        # Get the relative path of each path, create the directory in the build dir
        subdir_relative_path = subdir.relative_to(subdir.anchor)
        target_dir = self.build_dir / subdir_relative_path

        self._mkdir(target_dir)


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


def deploy_nodes(self) -> None:
    """ Generates specified device nodes. """
    if self.get('mknod_cpio'):
        self.logger.info("Skipping mknod generation, as mknod_cpio is specified")
        return

    from os import makedev, mknod
    from stat import S_IFCHR

    for node, config in self['nodes'].items():
        node_path_abs = Path(config['path'])

        node_path = self.build_dir / node_path_abs.relative_to(node_path_abs.anchor)
        node_mode = S_IFCHR | config['mode']

        try:
            mknod(node_path, mode=node_mode, device=makedev(config['major'], config['minor']))
            self.logger.info("Created device node '%s' at path: %s" % (node, node_path))
        except PermissionError as e:
            self.logger.error("Unable to create device node %s at path: %s" % (node, node_path))
            self.logger.info("`mknod_cpio` in `ugrd.base` can be used to generate device nodes within the initramfs archive if they cannot be created on the host system.")
            raise e


def configure_library_paths(self) -> None:
    """ Sets the export LD_LIBRARY_PATH variable to the library paths."""
    library_paths = ":".join(self['library_paths'])
    self.logger.debug("Setting LD_LIBRARY_PATH to: %s" % library_paths)
    return "export LD_LIBRARY_PATH=%s" % library_paths


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
        self.logger.debug("Binary already in binaries list, skipping: %s" % binary)
        return

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


def _process_dependencies_multi(self, dependency: Union[Path, str]) -> None:
    """
    Converts the input to a Path if it is not one, checks if it exists.
    If the dependency is a symlink, resolve it and add it to the symlinks list.
    """
    if not isinstance(dependency, Path):
        dependency = Path(dependency)

    if not dependency.exists():
        raise FileNotFoundError("Dependency does not exist: %s" % dependency)

    if dependency.is_symlink():
        if self['symlinks'].get(f'_auto_{dependency.name}'):
            self.logger.log(5, "Dependency is a symlink which is alreadty in the symlinks list, skipping: %s" % dependency)
        else:
            resolved_path = dependency.resolve()
            self.logger.debug("Dependency is a symlink, adding to symlinks: %s -> %s" % (dependency, resolved_path))
            self['symlinks'][f'_auto_{dependency.name}'] = {'source': resolved_path, 'target': dependency}
            dependency = resolved_path

    self.logger.debug("Adding dependency: %s" % dependency)
    self['dependencies'].append(dependency)


def _process_build_logging(self, log_build: bool) -> None:
    """ Sets the build log flag. """
    build_log_level = self.get('_build_log_level', 10)
    if log_build:
        self['_build_log_level'] = max(build_log_level + 10, 20)
    else:
        if self['_build_log_level'] > 10:
            self.logger.warning("Resetting _build_log_level to 10, as build logging is disabled.")
        self['_build_log_level'] = 10
    dict.__setitem__(self, 'build_logging', log_build)


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
        config['path'] = f"/dev/{name}"
        self.logger.debug("[%s] No path specified, assuming: %s" % (name, config['path']))

    if 'mode' not in config:
        config['mode'] = 0o660
        self.logger.debug("[%s] No mode specified, assuming: %s" % (name, config['mode']))

    self.logger.debug("[%s] Adding node: %s" % (name, config))
    self['nodes'][name] = config


def _process_file_owner(self, owner: Union[str, int]) -> None:
    """
    Processes the passed file owner into a uid.
    If the owner is a string, it is assumed to be a username and the uid is looked up.
    If the owner is an int, it is assumed to be a uid and is used directly.
    """
    from pwd import getpwnam

    if isinstance(owner, str):
        try:
            self.logger.debug("Processing file owner: %s" % owner)
            owner = getpwnam(owner).pw_uid
            self.logger.info("Resolved uid: %s" % owner)
        except KeyError as e:
            raise KeyError("Unable to find uid for user: %s" % owner) from e
    elif not isinstance(owner, int):
        self.logger.error("Unable to process file owner: %s" % owner)
        raise ValueError("Invalid type passed for file owner: %s" % type(owner))

    self['_file_owner_uid'] = owner
    dict.__setitem__(self, 'file_owner', owner)


def _process_masks_multi(self, runlevel: str, function: str) -> None:
    """ Processes a mask definition. """
    self.logger.debug("[%s] Adding mask: %s" % (runlevel, function))
    self['masks'][runlevel] = function

    if runlevel not in self['imports']:
        self.logger.warning("[%s] Masked runlevel not found in imports, skipping deletion: %s" % (runlevel, function))
    else:
        for func in self['imports'][runlevel]:
            if func.__name__ == function:
                self['imports'][runlevel].remove(func)
                self.logger.info("[%s] Removing function from runlevel: %s" % (runlevel, function))
                break
        else:
            self.logger.warning("[%s] Function not found in runlevel, skipping deletion: %s" % (runlevel, function))


def _process_hostonly(self, hostonly: bool) -> None:
    """
    Processes the hostonly parameter.
    If validation is enabled, and hostonly mode is set to disabled, disable validation and warn.
    """
    self.logger.debug("Processing hostonly: %s" % hostonly)
    dict.__setitem__(self, 'hostonly', hostonly)
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

    dict.__setitem__(self, 'validate', validate)

