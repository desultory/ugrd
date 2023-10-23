__author__ = 'desultory'

__version__ = '0.4.2'

from pathlib import Path


MODULE_METADATA_FILES = ['modules.alias', 'modules.alias.bin', 'modules.builtin', 'modules.builtin.alias.bin', 'modules.builtin.bin', 'modules.builtin.modinfo',
                         'modules.dep', 'modules.dep.bin', 'modules.devname', 'modules.order', 'modules.softdep', 'modules.symbols', 'modules.symbols.bin']


class IgnoredKernelModule(Exception):
    pass


class BuiltinKernelModule(Exception):
    pass


class DependencyResolutionError(Exception):
    pass


def _process_kmod_init_multi(self, module):
    """
    Adds init modules to self['kernel_modules'].
    """
    if module in self['kmod_ignore']:
        raise IgnoredKernelModule("Kernel module is in ignore list: %s" % module)

    self.logger.info("Adding kmod_init module to kernel_modules: %s", module)
    self['kernel_modules'] = module


def resolve_kmod_path(self, module_name):
    """
    Gets the file path of a kernel module
    """
    self.logger.debug("Resolving path for: %s" % module_name)
    args = ['modinfo', '--field', 'filename', module_name]

    if self.config_dict.get('kernel_version'):
        args += ['--set-version', self.config_dict['kernel_version']]

    try:
        cmd = self._run(args)
    except RuntimeError as e:
        raise DependencyResolutionError("Failed to get kernel module path for: %s" % module_name) from e

    module_path = cmd.stdout.decode('utf-8').strip()

    if module_path == '(builtin)':
        raise BuiltinKernelModule(module_name)

    self.logger.debug(f'Kernel module {module_name} is located at {module_path}')

    return Path(module_path)


def resolve_kmod_softdeps(self, module_name):
    """
    Gets all kernel module soft dependencies.
    """
    self.logger.debug("Resolving kernel module soft dependencies for: %s" % module_name)
    args = ['modinfo', '--field', 'softdep', module_name]

    if self.config_dict.get('kernel_version'):
        args += ['--set-version', self.config_dict['kernel_version']]

    try:
        cmd = self._run(args)
    except RuntimeError as e:
        raise DependencyResolutionError("Failed to get kernel module soft dependencies for: %s" % module_name) from e

    softdeps = cmd.stdout.decode().strip().split()
    if softdeps:
        softdeps = softdeps[1::2]
        self.logger.debug("Kernel module '%s' has soft dependencies: %s" % (module_name, softdeps))
        return softdeps


def resolve_kmod_harddeps(self, module_name):
    """
    Gets all kernel module dependencies.
    """

    self.logger.debug("Resolving kernel module dependencies for: %s" % module_name)
    args = ['modinfo', '--field', 'depends', module_name]

    if self.config_dict.get('kernel_version'):
        args += ['--set-version', self.config_dict['kernel_version']]

    try:
        cmd = self._run(args)
    except RuntimeError as e:
        raise DependencyResolutionError("Failed to get kernel module dependencies for: %s" % module_name) from e

    dependencies = cmd.stdout.decode().strip().split(',')

    if dependencies[0]:
        self.logger.debug("Kernel module '%s' has hard dependencies: %s" % (module_name, dependencies))
        return dependencies


def resolve_kmod(self, module_name):
    """
    Gets the file path of a single kernel module.
    Gets the file path of all dependencies if they exist
    """
    self.logger.debug("Resolving kernel module dependencies and path: %s" % module_name)
    if module_name in self.config_dict['kmod_ignore']:
        raise IgnoredKernelModule("Kernel module is in ignore list: %s" % module_name)

    dependencies = []

    if harddeps := resolve_kmod_harddeps(self, module_name):
        dependencies += harddeps

    if sofdeps := resolve_kmod_softdeps(self, module_name):
        if self.config_dict.get('kmod_ignore_softdeps', False):
            self.logger.warning("Soft dependencies were detected, but are being ignored: %s" % sofdeps)
        else:
            dependencies += sofdeps

    dependency_paths = []
    if dependencies:
        if any(dependency in self.config_dict['kmod_ignore'] for dependency in dependencies):
            self.logger.error("Kernel module '%s' has dependencies in ignore list: %s" % (module_name, dependencies))
            self.config_dict['kmod_ignore'] = module_name
            raise IgnoredKernelModule("Kernel module is in ignore list: %s" % module_name)

        self.logger.debug("Resolving dependencies: %s" % dependencies)
        for dependency in dependencies:
            try:
                dependency_paths.append(resolve_kmod_path(self, dependency))
                self.config_dict['kernel_modules'] = dependency
            except BuiltinKernelModule:
                self.logger.warning("[%s] Kernel module dependency is built-in: %s" % (module_name, dependency))
                self.config_dict['kmod_ignore'] = module_name

    try:
        dependency_paths.append(resolve_kmod_path(self, module_name))
        self.logger.debug("[%s] Calculated kernel module dependencies: %s" % (module_name, dependency_paths))
    except BuiltinKernelModule:
        self.logger.warning("[%s] Kernel module is built-in." % module_name)
        self.config_dict['kmod_ignore'] = module_name

    if dependency_paths:
        return dependency_paths
    else:
        self.logger.warning("[%s] Kernel module has no dependencies." % module_name)


def get_all_modules(self):
    """
    Gets the name of all currently installed kernel modules
    """
    try:
        cmd = self._run(['lsmod'])
    except RuntimeError as e:
        raise DependencyResolutionError('Failed to get list of kernel modules') from e

    raw_modules = cmd.stdout.decode('utf-8').split('\n')[1:]
    modules = []
    # Remove empty lines, header, and ignored modules
    for module in raw_modules:
        if not module:
            self.logger.log(5, "Dropping empty line")
        elif module.split()[0] == 'Module':
            self.logger.log(5, "Dropping header line")
        else:
            self.logger.debug("Adding kernel module: %s", module.split()[0])
            modules.append(module.split()[0])

    self.logger.debug(f'Found {len(modules)} active kernel modules')
    return modules


def get_module_metadata(self):
    """
    Gets all module metadata for the specified kernel version.
    Adds kernel module metadata files to dependencies.
    """
    if 'kernel_version' not in self.config_dict:
        self.logger.info("Kernel version not specified, using current kernel")
        try:
            cmd = self._run(['uname', '-r'])
        except RuntimeError as e:
            raise DependencyResolutionError('Failed to get kernel version') from e

        kernel_version = cmd.stdout.decode('utf-8').strip()
        self.logger.info(f'Using detected kernel version: {kernel_version}')
    else:
        kernel_version = self.config_dict['kernel_version']

    module_path = Path('/lib/modules/') / kernel_version

    for meta_file in MODULE_METADATA_FILES:
        meta_file_path = module_path / meta_file

        self.logger.debug("Adding kernel module metadata files to dependencies: %s", meta_file_path)
        self.config_dict['dependencies'] = meta_file_path


def calculate_modules(self):
    """
    Populates the kernel_modules list with all required kernel modules.
    Adds the contents of _kmod_depend if specified.
    If kernel_modules is empty, pulls all currently loaded kernel modules.
    """
    if not self.config_dict['kernel_modules']:
        self.logger.info("No kernel modules specified, adding all currently loaded kernel modules")
        self.config_dict['kernel_modules'] = get_all_modules(self)

    if self.config_dict['_kmod_depend']:
        self.logger.info("Adding internal dependencies to kernel modules: %s" % self.config_dict['_kmod_depend'])
        self.config_dict['kernel_modules'] += self.config_dict['_kmod_depend']

    self.logger.info("Fetching kernel modules: %s" % self.config_dict['kernel_modules'])

    for module in self.config_dict['kernel_modules']:
        self.logger.debug("Processing kernel module: %s" % module)
        if module in self.config_dict['kmod_ignore']:
            raise IgnoredKernelModule("Kernel module is in ignore list: %s" % module)

        try:
            if module_paths := resolve_kmod(self, module):
                self.config_dict['dependencies'] = module_paths
                self.logger.info("Resolved dependency paths for kernel module '%s': %s" % (module, module_paths))
            else:
                self.logger.warning("Failed to resolve dependency paths for kernel module '%s'" % module)
        except IgnoredKernelModule:
            self.logger.warning("Ignoring kernel module: %s" % module)

    get_module_metadata(self)


def load_modules(self):
    """
    Loads all kernel modules
    """
    # Start by using the kmod_init variable
    kmods = self.config_dict['kmod_init']

    # If it's empty, try to use kernel_modules, and fail by reading all kernel modules
    if not kmods:
        if kmods := self.config_dict.get('kernel_modules'):
            self.logger.info("Using kernel_modules as 'kmod_init'")
        else:
            self.logger.warning("No kernel modules specified, loading all")
            kmods = get_all_modules(self)

    # Finally, add the internal dependencies from _kmod_depend
    if depends := self.config_dict.get('_kmod_depend'):
        self.logger.info("Adding internal dependencies to kernel modules: %s" % depends)
        kmods += depends

    if self.config_dict.get('kmod_ignore'):
        self.logger.info("Ignoring kernel modules: %s" % self.config_dict['kmod_ignore'])
        kmod_init = [kmod for kmod in kmods if kmod not in self.config_dict['kmod_ignore']]
    else:
        kmod_init = kmods

    self.logger.info("Init kernel modules: %s" % kmod_init)

    if kmod_init != kmods:
        self.logger.warning("Ignoring kernel modules: %s" % (set(kmods) - set(kmod_init)))

    module_str = ' '.join(kmod_init)
    return [f"modprobe -av {module_str}"]

