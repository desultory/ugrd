__author__ = "desultory"
__version__ = "1.1.1"

from zenlib.util import check_dict


def start_shell(self) -> str:
    """ Start a bash shell at the start of the initramfs. """
    return ['if [ "$(readvar DEBUG)" != "1" ]; then',
            '    ewarn "Debug module is enabled, but DEBUG is not set to 1: $DEBUG"',
            '    return',
            'fi',
            'einfo "Starting debug shell"',
            'bash']


@check_dict('start_shell', value=True, message="Not enabling the debug shell, as the start_shell option is not set.")
def enable_debug(self) -> str:
    """ Enable debug mode. """
    return "setvar DEBUG 1"
