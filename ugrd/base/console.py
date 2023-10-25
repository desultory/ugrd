__author__ = "desultory"
__version__ = "0.3.5"


def custom_init(self):
    """
    init override
    """
    custom_init_contents = [self.config_dict['shebang'],
                            f"# Console module version v{__version__}"]
    custom_init_contents += self.generate_init_main()

    self._write("init_main.sh", custom_init_contents, 0o755)

    return console_init(self)


def console_init(self):
    """
    start agetty
    """
    name = self.config_dict['primary_console']
    out_str = f"agetty --autologin root --login-program /init_main.sh {name}"

    console = self.config_dict['console'][name]

    if console.get('local'):
        out_str += " -L"

    console_type = console.get('type', 'tty')

    if console_type != 'tty':
        baud_rate = console['baud']
        out_str += f" {console_type} {baud_rate}"
    else:
        out_str += f" {console_type}"

    return out_str

