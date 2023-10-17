__author__ = "desultory"
__version__ = "0.3.3"


def custom_init(self):
    """
    init override
    """
    from os import chmod
    with open(f"{self.out_dir}/init_main.sh", 'w', encoding='utf-8') as main_init:
        main_init.write("#!/bin/bash\n")
        [main_init.write(f"{line}\n") for line in self.generate_init_main()]
    chmod(f"{self.out_dir}/init_main.sh", 0o755)
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

    return [out_str]

