__author__ = "desultory"
__version__ = "1.1.0"

from zenlib.util import check_dict


def start_shell(self) -> str:
    """ Start a bash shell at the start of the initramfs. """
    return ['if [ "$(readvar DEBUG)" != "1" ]; then',
            '    return',
            'fi',
            'einfo "Starting debug shell"',
            'bash']


@check_dict('start_shell', value=True, message="Not enabling the debug shell, as the start_shell option is not set.")
def enable_debug(self) -> str:
    """ Enable debug mode. """
    return "export DEBUG=1"
