__author__ = "desultory"
__version__ = "1.2.0"

from zenlib.util import check_dict


def start_shell(self) -> str:
    """ Start a bash shell at the start of the initramfs. """
    return ['if ! check_var debug; then',
            '    ewarn "The debug module is enabled, but debug is not set enabled"',
            '    return',
            'fi',
            'einfo "Starting debug shell"',
            'bash']


@check_dict('start_shell', value=True, message="Not enabling the debug shell, as the start_shell option is not set.")
def enable_debug(self) -> str:
    """ Enable debug mode. """
    return "setvar debug 1"
