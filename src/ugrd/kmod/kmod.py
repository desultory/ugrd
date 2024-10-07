__author__ = 'desultory'
__version__ = '2.16.1'

from pathlib import Path
from subprocess import run

from zenlib.util import contains, unset
from ugrd.kmod import _normalize_kmod_name, BuiltinModuleError, DependencyResolutionError, IgnoredModuleError


MODULE_METADATA_FILES = ['modules.order', 'modules.builtin', 'modules.builtin.modinfo']


def _process_kernel_modules_multi(self, module: str) -> None:
    """ Adds kernel modules to self['kernel_modules']. """
    module = _normalize_kmod_name(module)
    if module in self['kmod_ignore']:
        self.logger.debug("[%s] Module is in the ignore list." % module)
        self['_kmod_removed'] = module
        return

    self.logger.debug("Adding kernel module to kernel_modules: %s", module)
    self['kernel_modules'].append(module)


def _process_kmod_init_multi(self, module: str) -> None:
    """ Adds init modules to self['kernel_modules']. """
    module = _normalize_kmod_name(module)
    if module in self['kmod_ignore']:
        raise IgnoredModuleError("kmod_init module is in the ignore list: %s" % module)
    self['kmod_init'].append(module)
    self.logger.debug("Adding kmod_init module to kernel_modules: %s", module)
    self['kernel_modules'] = module


def _process__kmod_auto_multi(self, module: str) -> None:
    """ Adds autodetected modules to self['kernel_modules']. """
    module = _normalize_kmod_name(module)
    if module in self['kmod_ignore']:
        self.logger.debug("Autodetected module is in the ignore list: %s" % module)
        self['_kmod_removed'] = module
        return
    self.logger.debug("Adding autodetected kernel module to kernel_modules: %s", module)
    self['_kmod_auto'].append(module)


def _get_kmod_info(self, module: str):
    """
    Runs modinfo on a kernel module, parses the output and stored the results in self['_kmod_modinfo'].
    !!! Should be run after metadata is processed so the kver is set properly !!!
    """
    module = _normalize_kmod_name(module)
    if module in self['_kmod_modinfo']:
        return self.logger.debug("[%s] Module info already exists." % module)
    args = ['modinfo', module, '--set-version', self['kernel_version']]

    try:
        self.logger.debug("[%s] Modinfo command: %s" % (module, ' '.join(args)))
        cmd = run(args, capture_output=True)
    except RuntimeError as e:
        raise DependencyResolutionError("[%s] Failed to run modinfo command: %s" % (module, ' '.join(args))) from e

    if not cmd.stdout and cmd.stderr:
        raise DependencyResolutionError("[%s] Modinfo returned no output." % module)

    module_info = {}
    for line in cmd.stdout.decode().split('\n'):
        line = line.strip()
        if line.startswith('filename:'):
            module_info['filename'] = line.split()[1]
        elif line.startswith('depends:') and line != 'depends:':
            if ',' in line:
                module_info['depends'] = _normalize_kmod_name(line.split(':')[1].lstrip().split(','))
            else:
                module_info['depends'] = _normalize_kmod_name([line.split()[1]])
        elif line.startswith('softdep:'):
            module_info['softdep'] = line.split()[2::2]
        elif line.startswith('firmware:'):
            # Firmware is a list, so append to it, making sure it exists first
            if 'firmware' not in module_info:
                module_info['firmware'] = []
            module_info['firmware'] += line.split()[1:]

    if not module_info.get('filename'):
        raise DependencyResolutionError("[%s] Failed to process modinfo output: %s" % (module, cmd.stdout.decode()))

    self.logger.debug("[%s] Module info: %s" % (module, module_info))
    self['_kmod_modinfo'][module] = module_info


@contains('kmod_autodetect_lspci', "kmod_autodetect_lspci is not enabled, skipping.")
def _autodetect_modules_lspci(self) -> None:
    """ Gets the name of all kernel modules being used by hardware visible in lspci -k. """
    try:
        cmd = self._run(['lspci', '-k'])
    except RuntimeError as e:
        raise DependencyResolutionError("Failed to get list of kernel modules") from e
    lspci_kmods = set()
    # Iterate over all output lines
    for line in cmd.stdout.decode('utf-8').split('\n'):
        # If the line contains the string 'Kernel modules:' or 'Kernel driver in use:', it contains the name of a kernel module
        if 'Kernel modules:' in line or 'Kernel driver in use:' in line:
            module = line.split(':')[1]
            if ',' in module:
                # If there are multiple modules, split them and add them to the module set
                for module in module.split(','):
                    lspci_kmods.add(module.strip())
            else:
                lspci_kmods.add(module.strip())

    self['_kmod_auto'] = list(lspci_kmods)


@contains('kmod_autodetect_lsmod', "kmod_autodetect_lsmod is not enabled, skipping.")
def _autodetect_modules_lsmod(self) -> None:
    """ Gets the name of all currently used kernel modules. """
    from platform import uname
    if self.get('kernel_version') and self['kernel_version'] != uname().release:
        self.logger.warning("Kernel version is set to %s, but the current kernel version is %s" % (self['kernel_version'], uname().release))

    with open('/proc/modules', 'r') as f:
        for module in f.readlines():
            self['_kmod_auto'] = module.split()[0]


@unset('no_kmod', "no_kmod is enabled, skipping.", log_level=30)
@contains('hostonly', "hostonly is not enabled, skipping.", log_level=30)
def autodetect_modules(self) -> None:
    """ Autodetects kernel modules from lsmod and/or lspci -k. """
    if not self['kmod_autodetect_lsmod'] and not self['kmod_autodetect_lspci']:
        self.logger.debug("No autodetection methods are enabled.")
        return
    _autodetect_modules_lsmod(self)
    _autodetect_modules_lspci(self)
    if self['_kmod_auto']:
        self.logger.info("Autodetected kernel modules: %s" % ', '.join(self['_kmod_auto']))
    else:
        self.logger.warning("No kernel modules were autodetected.")


def get_kernel_metadata(self) -> None:
    """ Gets metadata for all kernel modules. """
    if not self.get('kernel_version'):
        try:
            cmd = self._run(['uname', '-r'])
        except RuntimeError as e:
            raise DependencyResolutionError('Failed to get kernel version') from e

        self['kernel_version'] = cmd.stdout.decode('utf-8').strip()
        self.logger.info(f"Using detected kernel version: {self['kernel_version']}")

    self['_kmod_dir'] = Path('/lib/modules') / self['kernel_version']
    if not self['_kmod_dir'].exists():
        if self['no_kmod']:  # Just warn if no_kmod is set
            self.logger.warning("Kernel module directory does not exist, but no_kmod is set.")
        else:
            raise DependencyResolutionError(f"Kernel module directory does not exist for kernel: {self['kernel_version']}")


@contains('kmod_init', "kmod_init is empty, skipping.")
@unset('no_kmod', "no_kmod is enabled, skipping.", log_level=30)
def process_module_metadata(self) -> None:
    """ Adds kernel module metadata files to dependencies."""
    for meta_file in MODULE_METADATA_FILES:
        meta_file_path = self['_kmod_dir'] / meta_file

        self.logger.debug("[%s] Adding kernel module metadata files to dependencies: %s" % (self['kernel_version'], meta_file_path))
        self['dependencies'] = meta_file_path


@contains('kmod_init', "kmod_init is empty, skipping.")
@unset('no_kmod', "no_kmod is enabled, skipping.", log_level=30)
def regen_kmod_metadata(self) -> None:
    """ Regenerates kernel module metadata files using depmod. """
    self.logger.info("Regenerating kernel module metadata files.")
    build_dir = self._get_build_path('/')
    self._run(['depmod', '--basedir', build_dir, self['kernel_version']])


def _add_kmod_firmware(self, kmod: str) -> None:
    """ Adds firmware files for the specified kernel module to the initramfs. """
    kmod = _normalize_kmod_name(kmod)
    if kmod not in self['_kmod_modinfo']:
        raise DependencyResolutionError("Kernel module info does not exist: %s" % kmod)

    if self['_kmod_modinfo'][kmod].get('firmware') and not self['kmod_pull_firmware']:
        self.logger.warning("[%s] Kernel module has firmware files, but kmod_pull_firmware is not set." % kmod)

    if not self['_kmod_modinfo'][kmod].get('firmware') or not self.get('kmod_pull_firmware'):
        return

    for firmware in self['_kmod_modinfo'][kmod]['firmware']:
        _add_firmware_dep(self, kmod, firmware)


def _add_firmware_dep(self, kmod: str, firmware: str) -> None:
    """ Adds a kernel module firmware file to the initramfs dependencies. """
    kmod = _normalize_kmod_name(kmod)
    firmware_path = Path('/lib/firmware') / firmware
    if not firmware_path.exists():
        if firmware_path.with_suffix(firmware_path.suffix + '.xz').exists():
            firmware_path = firmware_path.with_suffix(firmware_path.suffix + '.xz')
            if self['kmod_decompress_firmware']:  # otherise, just add it like a normal dependency
                self['xz_dependencies'] = firmware_path
                return self.logger.debug("[%s] Found xz compressed firmware file: %s" % (kmod, firmware_path))
        else:
            # Really, this should be a huge error, but with xhci_pci, it wants some renesas firmware that's not in linux-firmware and doesn't seem to matter
            return self.logger.error("[%s] Firmware file does not exist: %s" % (kmod, firmware_path))
    self.logger.debug("[%s] Adding firmware file to dependencies: %s" % (kmod, firmware_path))
    self['dependencies'] = firmware_path


def _process_kmod_dependencies(self, kmod: str) -> None:
    """ Processes a kernel module's dependencies. """
    kmod = _normalize_kmod_name(kmod)
    _get_kmod_info(self, kmod)
    # Add dependencies of the module
    dependencies = []
    if harddeps := self['_kmod_modinfo'][kmod].get('depends'):
        dependencies += harddeps

    if sofdeps := self['_kmod_modinfo'][kmod].get('softdep'):
        if self.get('kmod_ignore_softdeps', False):
            self.logger.warning("[%s] Soft dependencies were detected, but are being ignored: %s" % (kmod, sofdeps))
        else:
            dependencies += sofdeps

    for dependency in dependencies:
        if dependency in self['kmod_ignore']:  # Don't add modules with ignored dependencies
            if modinfo := self['_kmod_modinfo'].get(dependency):
                if modinfo['filename'] != '(builtin)':  # But if it's ignored because it's built-in, that's fine
                    raise DependencyResolutionError("[%s] Kernel module dependency is in ignore list: %s" % (kmod, dependency))
        if dependency in self['kernel_modules']:
            self.logger.debug("[%s] Dependency is already in kernel_modules: %s" % (kmod, dependency))
            continue
        self.logger.debug("[%s] Processing dependency: %s" % (kmod, dependency))
        self['kernel_modules'] = dependency
        try:
            _process_kmod_dependencies(self, dependency)
        except BuiltinModuleError as e:
            self.logger.debug(e)
            continue

    if self['_kmod_modinfo'][kmod]['filename'] == '(builtin)':
        raise BuiltinModuleError("Not adding built-in module to dependencies: %s" % kmod)

    _add_kmod_firmware(self, kmod)

    filename = self['_kmod_modinfo'][kmod]['filename']
    if filename.endswith('.ko'):
        self['dependencies'] = filename
    elif filename.endswith('.ko.xz'):
        self['xz_dependencies'] = filename
    elif filename.endswith('.ko.gz'):
        self['gz_dependencies'] = filename
    else:
        self.logger.warning("[%s] Unknown kmod extension: %s" % (kmod, filename))
        self['dependencies'] = filename


def process_ignored_module(self, module: str) -> None:
    """ Processes an ignored module. """
    self.logger.debug("Removing kernel module from all lists: %s", module)
    for key in ['kmod_init', 'kernel_modules', '_kmod_auto']:
        if module in self[key]:
            if key == 'kmod_init':
                if module in self['_kmod_modinfo'] and self['_kmod_modinfo'][module]['filename'] == '(builtin)':
                    self.logger.debug("Removing built-in module from kmod_init: %s" % module)
                else:
                    raise ValueError("Required module cannot be imported and is not builtin: %s" % module)
            else:
                self.logger.debug("Removing ignored kernel module from %s: %s" % (key, module))
            self[key].remove(module)
            self['_kmod_removed'] = module


def process_ignored_modules(self) -> None:
    """ Processes all ignored modules. """
    for module in self['kmod_ignore']:
        process_ignored_module(self, module)


@unset('no_kmod', "no_kmod is enabled, skipping.", log_level=30)
def process_modules(self) -> None:
    """ Processes all kernel modules, adding dependencies to the initramfs. """
    self.logger.debug("Processing kernel modules: %s" % self['kernel_modules'])
    for kmod in self['kernel_modules'].copy():
        self.logger.debug("Processing kernel module: %s" % kmod)
        try:
            _process_kmod_dependencies(self, kmod)
            continue
        except BuiltinModuleError:
            if kmod in self['kmod_init']:
                self.logger.debug("Removing built-in module from kmod_init: %s" % kmod)
                self['kmod_init'].remove(kmod)
            self.logger.debug("Removing built-in module from kernel_modules: %s" % kmod)
            self['kernel_modules'].remove(kmod)
            continue  # Don't add built-in modules to the ignore list
        except IgnoredModuleError as e:
            self.logger.info(e)
        except DependencyResolutionError as e:
            if kmod in self['kmod_init']:
                self.logger.warning("[%s] Failed to get modinfo for init kernel module: %s" % (kmod, e))
            self.logger.debug("[%s] Failed to get modinfo for kernel module: %s" % (kmod, e))
        self['kmod_ignore'] = kmod

    for kmod in self['_kmod_auto']:
        if kmod in self['kernel_modules']:
            self.logger.debug("Autodetected module is already in kernel_modules: %s" % kmod)
            continue
        self.logger.debug("Processing autodetected kernel module: %s" % kmod)
        try:
            _process_kmod_dependencies(self, kmod)
            self['kmod_init'] = kmod
            continue
        except BuiltinModuleError:
            continue  # Don't add built-in modules to the ignore list
        except IgnoredModuleError as e:
            self.logger.debug(e)
        except DependencyResolutionError as e:
            self.logger.warning("[%s] Failed to process autodetected kernel module dependencies: %s" % (kmod, e))
        self['kmod_ignore'] = kmod


@contains('kmod_init', "No kernel modules to load.", log_level=30)
def load_modules(self) -> None:
    """ Creates a bash script which loads all kernel modules in kmod_init. """
    self.logger.info("Init kernel modules: %s" % ', '.join(self['kmod_init']))
    if included_kmods := list(set(self['kernel_modules']) ^ set(self['kmod_init'])):
        self.logger.info("Included kernel modules: %s" % ', '.join(included_kmods))
    if removed_kmods := self.get('_kmod_removed'):
        self.logger.warning("Ignored kernel modules: %s" % ', '.join(removed_kmods))

    module_list = ' '.join(self['kmod_init'])
    return ['if check_var quiet ; then',
            '    modprobe -aq %s' % module_list,
            'else',
            '    einfo "Loading kernel modules: %s"' % module_list,
            '    modprobe -av %s' % module_list,
            'fi']
