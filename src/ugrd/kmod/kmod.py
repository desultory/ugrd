__author__ = 'desultory'
__version__ = '1.1.1'

from pathlib import Path
from subprocess import run


MODULE_METADATA_FILES = ['modules.alias', 'modules.alias.bin', 'modules.builtin', 'modules.builtin.alias.bin', 'modules.builtin.bin', 'modules.builtin.modinfo',
                         'modules.dep', 'modules.dep.bin', 'modules.devname', 'modules.order', 'modules.softdep', 'modules.symbols', 'modules.symbols.bin']


class DependencyResolutionError(Exception):
    pass


def _process_kmod_ignore_multi(self, module: str) -> None:
    """
    Adds ignored modules to self['kmod_ignore'].
    Removes ignored modules from self['kmod_init'], self['kernel_modules'], and self['_kmod_depend'].
    Removes any firmware dependencies added by the ignored module.
    """
    self.logger.debug("Adding module to kmod_ignore: %s", module)
    self['kmod_ignore'].append(module)
    _remove_kmod(self, module, 'Ignored')


def _remove_kmod(self, module: str, reason: str) -> None:
    """ Removes a kernel module from all kernel module lists. """
    self.logger.log(5, "Removing kernel module from all lists: %s", module)
    other_keys = ['kmod_init', 'kernel_modules', '_kmod_depend']

    for key in other_keys:
        if module in self[key]:
            self.logger.debug("Removing %s kernel module from %s: %s" % (reason, key, module))
            self[key].remove(module)


def _process_kernel_modules_multi(self, module: str) -> None:
    """
    Adds the passed kernel module to self['kernel_modules']
    Checks if the module is ignored
    """
    if module in self['kmod_ignore']:
        self.logger.warning("Not adding ignored kernel module to kernel_modules: %s" % module)
        self._remove_kmod(module, 'Ignored')
        return

    try:
        _get_kmod_info(self, module)
    except DependencyResolutionError:
        if module in self['kmod_init'] or module in self['_kmod_depend']:
            raise DependencyResolutionError("Failed to get modinfo for kernel required module: %s" % module)
        self.logger.error("Failed to get modinfo for kernel module: %s" % module)
        self['kmod_ignore'] = module
        return

    self.logger.debug("Processing kernel module: %s" % module)
    modinfo = self['_kmod_modinfo'][module]

    # Add dependencies of the module
    dependencies = []
    if harddeps := modinfo.get('depends'):
        dependencies += harddeps

    if sofdeps := modinfo.get('softdep'):
        if self.get('kmod_ignore_softdeps', False):
            self.logger.warning("Soft dependencies were detected, but are being ignored: %s" % sofdeps)
        else:
            dependencies += sofdeps

    for dependency in dependencies:
        if dependency in self['kmod_ignore']:
            self.logger.error("Kernel module dependency is in ignore list: %s" % dependency)
            self['kmod_ignore'] = module
        self.logger.debug("[%s] Processing dependency: %s" % (module, dependency))
        self['kernel_modules'] = dependency

    if modinfo['filename'] == '(builtin)':
        self.logger.debug("[%s] Kernel module is built-in." % module)
        _remove_kmod(self, module, 'built-in')
    else:
        self.logger.debug("Adding kernel module to kernel_modules: %s", module)
        self['kernel_modules'].append(module)


def _process_kmod_init_multi(self, module: str) -> None:
    """ Adds init modules to self['kernel_modules']. """
    # First append it to kmod_init
    self['kmod_init'].append(module)
    self.logger.debug("Adding kmod_init module to kernel_modules: %s", module)
    # If it's an ignored module, kernel_modules processing will resolve that issue
    self['kernel_modules'] = module


def _get_kmod_info(self, module: str):
    """ Runs modinfo on a kernel module, parses the output and stored the results in self['_kmod_modinfo']. """
    if module in self['_kmod_modinfo']:
        self.logger.log(5, "Module info already exists for: %s" % module)
        return

    args = ['modinfo', module]
    # Set kernel version if it exists, otherwise use the running kernel
    if self.get('kernel_version'):
        args += ['--set-version', self['kernel_version']]

    try:
        self.logger.debug("[%s] Modinfo command: %s" % (module, ' '.join(args)))
        cmd = run(args, capture_output=True)
    except RuntimeError as e:
        raise DependencyResolutionError("[%s] Failed to run modinfo command: %s" % (module, ' '.join(args))) from e

    module_info = {}
    for line in cmd.stdout.decode().split('\n'):
        line = line.strip()
        if line.startswith('filename:'):
            module_info['filename'] = line.split()[1]
        elif line.startswith('depends:') and line != 'depends:':
            if ',' in line:
                module_info['depends'] = line.split(',')[1:]
            else:
                module_info['depends'] = [line.split()[1]]
        elif line.startswith('softdep:'):
            module_info['softdep'] = line.split()[2::2]
        elif line.startswith('firmware:'):
            # Firmware is a list, so append to it, making sure it exists first
            if 'firmware' not in module_info:
                module_info['firmware'] = []
            module_info['firmware'] += line.split()[1:]

    if not module_info:
        raise DependencyResolutionError("[%s] Failed to process modinfo output: %s" % (module, cmd.stdout.decode()))

    self.logger.debug("[%s] Module info: %s" % (module, module_info))
    self['_kmod_modinfo'][module] = module_info


def get_lspci_modules(self) -> list[str]:
    """ Gets the name of all kernel modules being used by hardware visible in lspci -k. """
    if not self['hostonly']:
        raise RuntimeError("lscpi module resolution is only available in hostonly mod")

    try:
        cmd = self._run(['lspci', '-k'])
    except RuntimeError as e:
        raise DependencyResolutionError("Failed to get list of kernel modules") from e

    modules = set()
    # Iterate over all output lines
    for line in cmd.stdout.decode('utf-8').split('\n'):
        # If the line contains the string 'Kernel modules:' or 'Kernel driver in use:', it contains the name of a kernel module
        if 'Kernel modules:' in line or 'Kernel driver in use:' in line:
            module = line.split(':')[1]
            if ',' in module:
                # If there are multiple modules, split them and add them to the module set
                for module in module.split(','):
                    modules.add(module.strip())
            else:
                # Add the single module to the module set
                modules.add(module.strip())

    self.logger.debug("Kernel modules in use by hardware: %s" % modules)
    return list(modules)


def get_lsmod_modules(self) -> list[str]:
    """
    Gets the name of all currently installed kernel modules
    """
    from platform import uname
    if not self['hostonly']:
        raise RuntimeError("lsmod module resolution is only available in hostonly mode")

    if self['kernel_version'] and self['kernel_version'] != uname().release:
        self.logger.warning("Kernel version is set to %s, but the current kernel version is %s" % (self['kernel_version'], uname().release))

    try:
        cmd = self._run(['lsmod'])
    except RuntimeError as e:
        raise DependencyResolutionError('Failed to get list of kernel modules') from e

    raw_modules = cmd.stdout.decode('utf-8').split('\n')[1:]
    modules = set()
    # Remove empty lines, header, and ignored modules
    for module in raw_modules:
        if not module:
            self.logger.log(5, "Dropping empty line")
        elif module.split()[0] == 'Module':
            self.logger.log(5, "Dropping header line")
        else:
            self.logger.debug("Adding kernel module: %s", module.split()[0])
            modules.add(module.split()[0])

    self.logger.debug(f'Found {len(modules)} active kernel modules')
    return list(modules)


def calculate_modules(self) -> None:
    """
    Populates the kernel_modules list with all required kernel modules.
    If kmod_autodetect_lsmod is set, adds the contents of lsmod if specified.
    If kmod_autodetect_lspci is set, adds the contents of lspci -k if specified.
    Autodetected modules are added to kmod_init

    Adds the contents of _kmod_depend if specified.
    Performs dependency resolution on all kernel modules.
    """
    if self['kmod_autodetect_lsmod']:
        autodetected_modules = get_lsmod_modules(self)
        self.logger.info("Autodetected kernel modules from lsmod: %s" % autodetected_modules)
        self['kmod_init'] = autodetected_modules

    if self['kmod_autodetect_lspci']:
        autodetected_modules = get_lspci_modules(self)
        self.logger.info("Autodetected kernel modules from lscpi -k: %s" % autodetected_modules)
        self['kmod_init'] = autodetected_modules

    if self['_kmod_depend']:
        self.logger.info("Adding internal dependencies to kmod_init: %s" % self['_kmod_depend'])
        self['kmod_init'] = self['_kmod_depend'].copy()  # Copy because _kmod_depend may shrink during iteration

    self.logger.info("Included kernel modules: %s" % self['kernel_modules'])


def process_module_metadata(self) -> None:
    """
    Gets all module metadata for the specified kernel version.
    Adds kernel module metadata files to dependencies.
    """
    if not self.get('kernel_version'):
        self.logger.info("Kernel version not specified, using current kernel")
        try:
            cmd = self._run(['uname', '-r'])
        except RuntimeError as e:
            raise DependencyResolutionError('Failed to get kernel version') from e

        kernel_version = cmd.stdout.decode('utf-8').strip()
        self.logger.info(f'Using detected kernel version: {kernel_version}')
    else:
        kernel_version = self['kernel_version']

    module_path = Path('/lib/modules/') / kernel_version

    for meta_file in MODULE_METADATA_FILES:
        meta_file_path = module_path / meta_file

        self.logger.debug("Adding kernel module metadata files to dependencies: %s", meta_file_path)
        self['dependencies'] = meta_file_path


def process_modules(self) -> None:
    """ Processes all kernel modules, adding dependencies to the initramfs. """
    for kmod in self['kernel_modules']:
        self.logger.debug("Processing kernel module: %s" % kmod)
        modinfo = self['_kmod_modinfo'][kmod]
        # Add the module itself to the dependencies
        self['dependencies'] = Path(modinfo['filename'])
        # If the module has firmware, add it to the dependencies
        if firmware := modinfo.get('firmware'):
            if self.get('kmod_pull_firmware'):
                self.logger.info("[%s] Adding firmware to dependencies: %s" % (kmod, firmware))
                for file in firmware:
                    try:
                        self['dependencies'] = Path('/lib/firmware/') / file
                    except FileNotFoundError:
                        self.logger.warning("[%s] Unable to find referenced firmware file: %s" % (kmod, file))
            else:
                self.logger.warning("Firmware was detected, but is being ignored: %s" % firmware)


def load_modules(self) -> None:
    """ Creates a bash script which loads all kernel modules in kmod_init. """
    # Start by using the kmod_init variable
    kmods = self['kmod_init']

    if not kmods:
        self.logger.error("No kernel modules to load")
        return

    self.logger.info("Init kernel modules: %s" % kmods)
    self.logger.warning("Ignored kernel modules: %s" % self['kmod_ignore'])

    module_str = ' '.join(kmods)
    return f"modprobe -av {module_str}"

