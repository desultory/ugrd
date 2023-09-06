__author__ = 'desultory'

__version__ = '0.1.5'

from subprocess import run


def resolve_kmod(self, module_name):
    """
    Gets the file path of a kernel module
    """
    cmd = run(['modinfo', '--field', 'filename', module_name], capture_output=True)
    if cmd.returncode != 0:
        self.logger.error(f'Kernel module {module_name} not found')
        self.logger.debug(f'Error: {cmd.stderr.decode("utf-8").strip()}')
        return

    module_path = cmd.stdout.decode('utf-8').strip()

    if module_path == '(builtin)':
        self.logger.info(f'Kernel module {module_name} is built-in')
        return

    self.logger.debug(f'Kernel module {module_name} is located at {module_path}')

    return module_path


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
    modules = [module.split()[0] for module in modules if module and module.split()[0] != 'Module']

    self.logger.info(f'Found {len(modules)} active kernel modules')
    return modules


def fetch_modules(self):
    """
    Fetches all kernel modules
    """
    modules = self.config_dict.get('kernel_modules', get_all_modules(self))

    for module in modules:
        if module_path := resolve_kmod(self, module):
            self.config_dict['dependencies'].append(module_path)
        else:
            self.logger.warning(f'Failed to add kernel module {module} to dependencies')
