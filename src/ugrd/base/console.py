__author__ = "desultory"
__version__ = "1.3.0"


def custom_init(self) -> list[str]:
    """ init override for the console module.
    Adds the shebang to the top of the file, runs the banner, followed by
    most of the main init runlevels
    Write the main init runlevels to self._custom_init_file.
    Returns the output of console_init which is the command to start agetty.
    """
    custom_init_contents = [
        self["shebang"],
        f'einfo "Starting console module v{__version__}"',
        "print_banner",
        *self.generate_init_main(),
    ]

    return console_init(self), custom_init_contents


def console_init(self) -> list[str]:
    """ Returns the command to start agetty on the primary console.
    If the console is a serial port, set the baud rate.
    """
    name = self["primary_console"]
    console = self["console"][name]

    out_str = f"agetty --autologin root --login-program {self['_custom_init_file']}"

    console_type = console.get("type", "tty")
    if console_type != "tty":
        # This differs from usage in the man page but seems to work?
        out_str += f" --local-line {console['baud']}"

    out_str += f" {name} {console_type} || rd_restart"

    return out_str
