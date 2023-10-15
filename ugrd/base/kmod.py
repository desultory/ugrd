__author__ = 'desultory'

__version__ = '0.3.0'

from subprocess import run

MODULE_METADATA_FILES = ['modules.alias', 'modules.alias.bin', 'modules.builtin', 'modules.builtin.alias.bin', 'modules.builtin.bin', 'modules.builtin.modinfo',
                         'modules.dep', 'modules.dep.bin', 'modules.devname', 'modules.order', 'modules.softdep', 'modules.symbols', 'modules.symbols.bin']


def resolve_kmod_path(self, module_name):
    """
    Gets the file path of a kernel module
    """
    args = ['modinfo', '--field', 'filename', module_name]

    if self.config_dict.get('kernel_version'):
        args += ['--set-version', self.config_dict['kernel_version']]

    cmd = run(args, capture_output=True)
    if cmd.returncode != 0:
        self.logger.error("Failed to get kernel module path for: %s" % module_name)
        return

    module_path = cmd.stdout.decode('utf-8').strip()

    if module_path == '(builtin)':
        self.logger.info(f'Kernel module {module_name} is built-in')
        return

    self.logger.debug(f'Kernel module {module_name} is located at {module_path}')

    return module_path


def resolve_kmod(self, module_name):
    """
    Gets the file path of a single kernel module.
    Gets the file path of all dependenceis of they exist
    """
    if module_name in self.config_dict['kmod_ignore']:
        raise ValueError("Kernel module is in ignore list: %s" % module_name)

    self.logger.debug("Resolving kernel module dependencies for: %s" % module_name)
    args = ['modinfo', '--field', 'depends', module_name]

    if self.config_dict.get('kernel_version'):
        args += ['--set-version', self.config_dict['kernel_version']]

    cmd = run(args, capture_output=True)
    if cmd.returncode != 0:
        self.logger.error("Failed to get kernel module dependencies for: %s" % module_name)
        return

    dependencies = cmd.stdout.decode('utf-8').strip().split(',')

    if not dependencies[0]:
        self.logger.debug('Kernel module has no dependencies: %s' % module_name)
        return resolve_kmod_path(self, module_name)
    else:
        dependency_paths = []
        if any(dependency in self.config_dict['kmod_ignore'] for dependency in dependencies):
            self.logger.warning("Kernel module '%s' has dependencies in ignore list: %s" % (module_name, dependencies))
            self.config_dict['kmod_ignore'].append(module_name)
            return

        self.logger.debug("Kernel module '%s' has dependencies: %s" % (module_name, dependencies))
        for dependency in dependencies:
            if dependency_path := resolve_kmod(self, dependency):
                dependency_paths.append(dependency_path)
            else:
                self.logger.error("Failed to resolve kernel module dependency: %s" % dependency)
                self.config_dict['kmod_ignore'].append(module_name)
                return
        dependency_paths.append(resolve_kmod_path(self, module_name))
        self.logger.debug("Calculated kernel module dependencies for '%s': %s" % (module_name, dependency_paths))
        return dependency_paths


def get_all_modules(self):
    """
    Gets the name of all currently installed kernel modules
    """
    cmd = run(['lsmod'], capture_output=True)
    if cmd.returncode != 0:
        self.logger.error('Failed to get list of kernel modules')
        self.logger.debug(f'Error: {cmd.stderr.decode("utf-8").strip()}')
        return

    modules = cmd.stdout.decode('utf-8').split('\n')[1:]
    modules = [module.split()[0] for module in modules if module and module.split()[0] != 'Module' and module.split()[0] not in self.config_dict['kmod_ignore']]

    self.logger.debug(f'Found {len(modules)} active kernel modules')
    return modules


def get_module_metadata(self):
    """
    Gets all module metadata for the specified kernel version
    """
    from pathlib import Path

    if 'kernel_version' not in self.config_dict:
        self.logger.debug("Kernel version not specified, using current kernel")
        cmd = run(['uname', '-r'], capture_output=True)
        if cmd.returncode != 0:
            self.logger.error('Failed to get kernel version')
            self.logger.debug(f'Error: {cmd.stderr.decode("utf-8").strip()}')
            return

        kernel_version = cmd.stdout.decode('utf-8').strip()
        self.logger.info(f'Using detected kernel version: {kernel_version}')
    else:
        kernel_version = self.config_dict['kernel_version']

    module_path = Path('/lib/modules/') / kernel_version

    for meta_file in MODULE_METADATA_FILES:
        meta_file_path = module_path / meta_file

        self.logger.debug("Adding kernel module metadata files to dependencies: %s", meta_file_path)
        self.config_dict['dependencies'].append(meta_file_path)


def fetch_modules(self):
    """
    Fetches all kernel modules
    """
    if 'kernel_modules' not in self.config_dict or not self.config_dict['kernel_modules']:
        self.logger.info("No kernel modules specified, fetching all")
        self.config_dict['kernel_modules'] = get_all_modules(self)

    self.logger.info("Fetching kernel modules: %s" % self.config_dict['kernel_modules'])

    for module in self.config_dict['kernel_modules']:
        if module in self.config_dict['kmod_ignore']:
            self.logger.info("Ignoring kernel module: %s" % module)
        elif module_paths := resolve_kmod(self, module):
            self.config_dict['dependencies'].append(module_paths)
            self.logger.info("Resolved dependency paths for kernel module '%s': %s" % (module, module_paths))
        else:
            self.logger.error("Failed to resolve dependencies for: %s" % module)

    get_module_metadata(self)


def load_modules(self):
    """
    Loads all kernel modules
    """
    kmods = self.config_dict['kmod_init']

    if not kmods:
        if kmods := self.config_dict.get('kernel_modules'):
            self.logger.info("Using kernel_modules as 'kmod_init'")
        else:
            kmods = get_all_modules(self)

    if self.config_dict.get('kmod_ignore'):
        self.logger.info("Ignoring kernel modules: %s" % self.config_dict['kmod_ignore'])
        kmods = [kmod for kmod in kmods if kmod not in self.config_dict['kmod_ignore']]

    self.logger.info("Init kernel modules: %s" % kmods)

    module_str = ' '.join(kmods)
    return [f"modprobe -av {module_str}"]

