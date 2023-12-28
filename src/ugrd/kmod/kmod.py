__author__ = 'desultory'
__version__ = '1.3.2'

from pathlib import Path
from subprocess import run


MODULE_METADATA_FILES = ['modules.alias', 'modules.alias.bin', 'modules.builtin', 'modules.builtin.alias.bin', 'modules.builtin.bin', 'modules.builtin.modinfo',
                         'modules.dep', 'modules.dep.bin', 'modules.devname', 'modules.order', 'modules.softdep', 'modules.symbols', 'modules.symbols.bin']


class DependencyResolutionError(Exception):
    pass


class BuiltinModuleError(Exception):
    pass


def _process_kmod_ignore_multi(self, module: str) -> None:
    """ Adds ignored modules to self['kmod_ignore']. Removes module from kmod_init and kernel_modules. """
    self.logger.debug("Adding module to kmod_ignore: %s", module)
    self['kmod_ignore'].append(module)

    self.logger.log(5, "Removing kernel module from all lists: %s", module)
    for key in ['kmod_init', 'kernel_modules']:
        if module in self[key]:
            self.logger.warning("Removing ignored kernel module from %s: %s" % (key, module))
            self[key].remove(module)
            self['_kmod_removed'] = module


def _process_kmod_init_multi(self, module: str) -> None:
    """ Adds init modules to self['kernel_modules']. """
    if module in self['kmod_ignore']:
        self.logger.debug("[%s] Module is in ignore list." % module)
        return
    # First append it to kmod_init
    self['kmod_init'].append(module)
    self.logger.debug("Adding kmod_init module to kernel_modules: %s", module)
    self['kernel_modules'] = module


def _get_kmod_info(self, module: str):
    """
    Runs modinfo on a kernel module, parses the output and stored the results in self['_kmod_modinfo'].
    Should be run after metadata is processed so the kver is set properly.
    """
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


def _get_lspci_modules(self) -> list[str]:
    """ Gets the name of all kernel modules being used by hardware visible in lspci -k. """
    if not self['hostonly']:
        raise RuntimeError("lscpi module resolution is only available in hostonly mode.")

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


def _get_lsmod_modules(self) -> list[str]:
    """ Gets the name of all currently installed kernel modules """
    from platform import uname
    if not self['hostonly']:
        raise RuntimeError("lsmod module resolution is only available in hostonly mode.")

    if self.get('kernel_version') and self['kernel_version'] != uname().release:
        self.logger.warning("Kernel version is set to %s, but the current kernel version is %s" % (self['kernel_version'], uname().release))

    try:
        cmd = self._run(['lsmod'])
    except RuntimeError as e:
        raise DependencyResolutionError('Failed to get list of kernel modules') from e

    raw_modules = cmd.stdout.decode('utf-8').split('\n')[1:]
    modules = set()
    # Remove empty lines, header
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
    """
    if self['kmod_autodetect_lsmod']:
        autodetected_modules = _get_lsmod_modules(self)
        self.logger.info("Autodetected kernel modules from lsmod: %s" % autodetected_modules)
        self['kmod_init'] = autodetected_modules

    if self['kmod_autodetect_lspci']:
        autodetected_modules = _get_lspci_modules(self)
        self.logger.info("Autodetected kernel modules from lscpi -k: %s" % autodetected_modules)
        self['kmod_init'] = autodetected_modules


def process_module_metadata(self) -> None:
    """
    Gets all module metadata for the specified kernel version.
    Adds kernel module metadata files to dependencies.
    Sets the kernel version based on the current running kernel if it's not already set.
    """
    if not self.get('kernel_version'):
        try:
            cmd = self._run(['uname', '-r'])
        except RuntimeError as e:
            raise DependencyResolutionError('Failed to get kernel version') from e

        self['kernel_version'] = cmd.stdout.decode('utf-8').strip()
        self.logger.info(f"Using detected kernel version: {self['kernel_version']}")

    module_path = Path('/lib/modules/') / self['kernel_version']

    for meta_file in MODULE_METADATA_FILES:
        meta_file_path = module_path / meta_file

        self.logger.debug("[%s] Adding kernel module metadata files to dependencies: %s" % (self['kernel_version'], meta_file_path))
        self['dependencies'] = meta_file_path


def _add_kmod_firmware(self, kmod: str) -> None:
    """ Adds firmware files for the specified kernel module to the initramfs. """
    if kmod not in self['_kmod_modinfo']:
        raise ValueError("Kernel module not found in _kmod_modinfo: %s" % kmod)

    if not self['_kmod_modinfo'][kmod].get('firmware') or not self.get('kmod_pull_firmware'):
        return

    if self['_kmod_modinfo'][kmod].get('firmware') and self['kmod_pull_firmware']:
        self.logger.warning("[%s] Kernel module has firmware files, but kmod_pull_firmware is not set." % kmod)

    for firmware in self['_kmod_modinfo'][kmod]['firmware']:
        firmware_path = Path('/lib/firmware') / firmware
        self.logger.debug("[%s] Adding firmware file to dependencies: %s" % (kmod, firmware_path))
        self['dependencies'] = firmware_path


def _process_kmod_dependencies(self, kmod: str) -> None:
    """ Processes a kernel module's dependencies. """
    if kmod not in self['_kmod_modinfo']:
        _get_kmod_info(self, kmod)

    # Add dependencies of the module
    dependencies = []
    if harddeps := self['_kmod_modinfo'][kmod].get('depends'):
        dependencies += harddeps

    if sofdeps := self['_kmod_modinfo'][kmod].get('softdep'):
        if self.get('kmod_ignore_softdeps', False):
            self.logger.warning("Soft dependencies were detected, but are being ignored: %s" % sofdeps)
        else:
            dependencies += sofdeps

    for dependency in dependencies:
        if dependency in self['kmod_ignore']:
            raise DependencyResolutionError("Kernel module dependency is in ignore list: %s" % dependency)
        self.logger.debug("[%s] Processing dependency: %s" % (kmod, dependency))
        self['kernel_modules'] = dependency
        _get_kmod_info(self, dependency)
        _process_kmod_dependencies(self, dependency)

    if self['_kmod_modinfo'][kmod]['filename'] == '(builtin)':
        raise BuiltinModuleError("Not adding built-in module to dependencies: %s" % kmod)

    self['dependencies'] = self['_kmod_modinfo'][kmod]['filename']
    _add_kmod_firmware(self, kmod)


def process_modules(self) -> None:
    """ Processes all kernel modules, adding dependencies to the initramfs. """
    self.logger.debug("Processing kernel modules: %s" % self['kernel_modules'])
    for kmod in self['kernel_modules'].copy():
        self.logger.debug("Processing kernel module: %s" % kmod)
        try:
            _process_kmod_dependencies(self, kmod)
            continue
        except BuiltinModuleError as e:
            self.logger.info(e)
        except DependencyResolutionError as e:
            if kmod in self['kmod_init']:
                self.logger.warning("[%s] Failed to get modinfo for init kernel module: %s" % (kmod, e))
            self.logger.debug("[%s] Failed to get modinfo for kernel module: %s" % (kmod, e))
        self['kmod_ignore'] = kmod


def load_modules(self) -> None:
    """ Creates a bash script which loads all kernel modules in kmod_init. """
    # Start by using the kmod_init variable
    kmods = self['kmod_init']

    if not kmods:
        self.logger.error("No kernel modules to load")
        return

    self.logger.info("Init kernel modules: %s" % kmods)
    self.logger.warning("Ignored kernel modules: %s" % self['_kmod_removed'])

    module_str = ' '.join(kmods)
    return f"modprobe -av {module_str}"

