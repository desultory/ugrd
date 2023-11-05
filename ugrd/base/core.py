__author__ = 'desultory'
__version__ = '1.1.0'

from pathlib import Path


def calculate_dependencies(self, binary):
    from shutil import which
    from subprocess import run

    binary_path = which(binary)
    if not binary_path:
        raise RuntimeError("'%s' not found in PATH" % binary)

    dependencies = run(['lddtree', '-l', binary_path], capture_output=True)
    if dependencies.returncode != 0:
        self.logger.warning("Unable to calculate dependencies for: %s" % binary)
        raise RuntimeError("Unable to resolve dependencies, error: %s" % dependencies.stderr.decode('utf-8'))

    dependency_paths = []
    for dependency in dependencies.stdout.decode('utf-8').splitlines():
        # Remove extra slash at the start if it exists
        if dependency.startswith('//'):
            dependency = dependency[1:]

        dep_path = Path(dependency)
        dependency_paths.append(dep_path)

    return dependency_paths


def deploy_dependencies(self):
    """
    Copies all dependencies to the build directory
    """
    for dependency in self.config_dict['dependencies']:
        self.logger.debug("Copying dependency: %s" % dependency)
        self._copy(dependency)


def deploy_copies(self):
    """
    Copiues everything from self.config_dict['copies'] into the build directory
    """
    for copy_name, copy_parameters in self.config_dict['copies'].items():
        self.logger.debug("[%s] Copying: %s" % (copy_name, copy_parameters))
        self._copy(copy_parameters['source'], copy_parameters['destination'])


def deploy_symlinks(self):
    """
    Creates symlinks for all symlinks in self.config_dict['symlinks']
    """
    for symlink_name, symlink_parameters in self.config_dict['symlinks'].items():
        self.logger.debug("[%s] Creating symlink: %s" % (symlink_name, symlink_parameters))
        self._symlink(symlink_parameters['source'], symlink_parameters['target'])


def deploy_nodes(self):
    """
    Generates specified device nodes
    """
    if self.config_dict.get('mknod_cpio'):
        self.logger.warning("Skipping mknod generation, as mknod_cpio is specified")
        return

    from os import makedev, mknod
    from stat import S_IFCHR

    for node, config in self.config_dict['nodes'].items():
        node_path_abs = Path(config['path'])

        node_path = self.config_dict['build_dir'] / node_path_abs.relative_to(node_path_abs.anchor)
        node_mode = S_IFCHR | config['mode']

        try:
            mknod(node_path, mode=node_mode, device=makedev(config['major'], config['minor']))
            self.logger.info("Created device node %s at path: %s" % (node, node_path))
        except PermissionError as e:
            self.logger.error("Unable to create device node %s at path: %s" % (node, node_path))
            self.logger.info("`mknod_cpio` in `ugrd.base` can be used to generate device nodes within the initramfs archive if they cannot be created on the host system.")
            raise e


def configure_library_paths(self):
    """
    Sets the export LD_LIBRARY_PATH variable to the library paths
    """
    library_paths = ":".join(self.config_dict['library_paths'])
    self.logger.debug("Setting LD_LIBRARY_PATH to: %s" % library_paths)
    return "export LD_LIBRARY_PATH=%s" % library_paths


def _process_paths_multi(self, path):
    """
    Converts the input to a Path if it is not one
    """
    self.logger.log(5, "Processing path: %s" % path)
    if not isinstance(path, Path):
        path = Path(path)

    self.logger.debug("Adding path: %s" % path)
    self['paths'].append(path)


def _process_binaries_multi(self, binary):
    """
    Processes binaries into the binaries list, adding dependencies along the way.
    """
    self.logger.debug("Processing binary: %s" % binary)

    dependencies = calculate_dependencies(self, binary)
    # The first dependency will be the path of the binary itself, don't add this to the library paths
    first_dep = True
    for dependency in dependencies:
        self['dependencies'] = dependency
        if first_dep:
            self.logger.debug("Skipping adding library path for first dependency: %s" % dependency)
            first_dep = False
            continue
        if str(dependency.parent) not in self['library_paths']:
            self.logger.info("Adding library path: %s" % dependency.parent)
            # Make it a string so NoDupFlatList can handle it
            # It being derived from a path should ensure it's a proper path
            self['library_paths'] = str(dependency.parent)

    self.logger.debug("Adding binary: %s" % binary)
    self['binaries'].append(binary)


def _process_dependencies_multi(self, dependency):
    """
    Converts the input to a Path if it is not one, checks if it exists
    """
    if not isinstance(dependency, Path):
        dependency = Path(dependency)

    if not dependency.exists():
        raise FileNotFoundError("Dependency does not exist: %s" % dependency)

    self.logger.debug("Adding dependency: %s" % dependency)
    self['dependencies'].append(dependency)


def _process_copies_multi(self, copy_name, copy_parameters):
    """
    Processes a copy from the copies parameter
    Ensures the source and target are defined in the parameters.
    """
    self.logger.log(5, "[%s] Processing copies: %s" % (copy_name, copy_parameters))
    if 'source' not in copy_parameters:
        raise ValueError("[%s] No source specified" % copy_name)
    if 'destination' not in copy_parameters:
        raise ValueError("[%s] No target specified" % copy_name)

    self.logger.debug("[%s] Adding copies: %s" % (copy_name, copy_parameters))
    self['copies'][copy_name] = copy_parameters


def _process_symlinks_multi(self, symlink_name, symlink_parameters):
    """
    Processes a symlink,
    Ensures the source and target are defined in the parameters.
    """
    self.logger.log(5, "[%s] Processing symlink: %s" % (symlink_name, symlink_parameters))
    if 'source' not in symlink_parameters:
        raise ValueError("[%s] No source specified" % symlink_name)
    if 'target' not in symlink_parameters:
        raise ValueError("[%s] No target specified" % symlink_name)

    self.logger.debug("[%s] Adding symlink: %s -> %s" % (symlink_name, symlink_parameters['source'], symlink_parameters['target']))
    self['symlinks'][symlink_name] = symlink_parameters


def _process_nodes_multi(self, node_name, node_config):
    """
    Process a device node
    """
    if 'major' not in node_config:
        raise ValueError("[%s] No major specified" % node_name)
    if 'minor' not in node_config:
        raise ValueError("[%s] No minor specified" % node_name)

    if 'path' not in node_config:
        node_config['path'] = f"/dev/{node_name}"
        self.logger.debug("[%s] No path specified, assuming: %s" % (node_name, node_config['path']))

    if 'mode' not in node_config:
        node_config['mode'] = 0o660
        self.logger.debug("[%s] No mode specified, assuming: %s" % (node_name, node_config['mode']))

    self.logger.debug("[%s] Adding node: %s" % (node_name, node_config))
    self['nodes'][node_name] = node_config


def _process_file_owner(self, owner):
    """
    Processes the passed file owner into a uid
    """
    from pwd import getpwnam

    if isinstance(owner, str):
        try:
            self.logger.debug("Processing file owner: %s" % owner)
            self['_file_owner_uid'] = getpwnam(owner).pw_uid
            self.logger.info("Detected file owner uid: %s" % self['_file_owner_uid'])
        except KeyError as e:
            self.logger.error("Unable to process file owner: %s" % owner)
            self.logger.error(e)
    elif isinstance(owner, int):
        self['_file_owner_uid'] = owner
        self.logger.info("Set file owner uid: %s" % self['_file_owner_uid'])
    else:
        self.logger.error("Unable to process file owner: %s" % owner)
        raise ValueError("Invalid type passed for file owner: %s" % type(owner))

