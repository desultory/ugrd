__author__ = "desultory"
__version__ = "1.3.0"


def start_shell(self) -> str:
    """ Start a bash shell at the start of the initramfs. """
    return ['if ! check_var debug; then',
            '    ewarn "The debug module is enabled, but debug is not set enabled"',
            '    return',
            'fi',
            'einfo "Starting debug shell"',
            'bash -l']


def enable_debug(self) -> str:
    """ Enable debug mode. """
    self._dict_contains('start_shell', message="Not enabling the debug shell, as the start_shell option is not set.", log_level=30)
    return "setvar debug 1"
