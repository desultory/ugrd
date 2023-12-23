__author__ = "desultory"
__version__ = "0.6.0"


def custom_init(self) -> str:
    """
    init override for the console module.
    Write the main init runlevels to self._custom_init_file.
    Returns the output of console_init which is the command to start agetty.
    """
    custom_init_contents = [self['shebang'],
                            f"# Console module version v{__version__}",
                            *self.generate_init_main()]

    return console_init(self), custom_init_contents


def console_init(self) -> str:
    """
    Start agetty on the primary console.
    Tell it to execute teh _custom_init_file
    If the console is a serial port, set the baud rate.
    """
    name = self['primary_console']
    console = self['console'][name]

    out_str = f"agetty --autologin root --login-program {self['_custom_init_file']}"

    console_type = console.get('type', 'tty')

    if console_type != 'tty':
        # This differs from usage in the man page but seems to work?
        out_str += f" --local-line {console['baud']}"

    out_str += f" {name} {console_type}"

    return out_str

