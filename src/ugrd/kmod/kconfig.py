__author__ = 'desultory'
__version__ = '0.1.0'

from zenlib.util import contains


def _normalize_kconfig_option(self, option: str) -> str:
    """ Normalizes a kernel config option. """
    option = option.upper()
    if not option.startswith('CONFIG_'):
        option = 'CONFIG_' + option
    return option


@contains('kernel_config_file', "Cannot check config, kernel config file not found.")
def _check_kernel_config(self, option: str):
    """
    Checks if an option is set in the kernel config file.
    Checks that the line starts with the option, and is set to 'y' or 'm'.
    If a match is found, return the line, otherwise return None
    """
    option = _normalize_kconfig_option(self, option)
    with open(self['kernel_config_file'], 'r') as f:
        for line in f.readlines():
            if line.startswith(option):
                if line.split('=')[1].strip()[0] in ['y', 'm']:
                    self.logger.debug("Kernel config option is set: %s" % option)
                    return line
                else:
                    return self.logger.debug("Kernel config option is not set: %s" % option)
    self.logger.debug("Kernel config option not found: %s" % option)


def find_kernel_config(self) -> None:
    """ Tries to find the kernel config file associated with the current kernel version. """
    build_dir = self['_kmod_dir'] / 'build'
    source_dir = self['_kmod_dir'] / 'source'
    for d in [build_dir, source_dir]:
        if d.exists():
            config_file = d / '.config'
            if config_file.exists():
                self.logger.info("Found kernel config file: %s" % config_file)
                self['kernel_config_file'] = config_file
                break
    else:
        self.logger.warning("Kernel config file not found.")
