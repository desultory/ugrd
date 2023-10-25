__author__ = "desultory"
__version__ = "0.4.0"


def custom_init(self):
    """
    init override for the console module.
    Write the main init runlevels to the self.config_dict['_custom_init_file'] file.
    Returns the output of console_init which is the command to start agetty.
    """
    custom_init_contents = [self.config_dict['shebang'],
                            f"# Console module version v{__version__}"]
    custom_init_contents += self.generate_init_main()

    self._write(self.config_dict['_custom_init_file'], custom_init_contents, 0o755)
    return console_init(self)


def console_init(self):
    """
    Start agetty on the primary console.
    Tell it to execute teh _custom_init_file
    If the console is a serial port, set the baud rate.
    """
    name = self.config_dict['primary_console']
    console = self.config_dict['console'][name]

    out_str = f"agetty --autologin root --login-program {self.config_dict['_custom_init_file']}"

    if console.get('local'):
        out_str += " --local-line=auto"

    out_str += f" {name}"

    console_type = console.get('type', 'tty')

    if console_type != 'tty':
        out_str += f" {console['baud']}"

    out_str += f" {console_type}"

    return out_str

