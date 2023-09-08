__author__ = "desultory"
__version__ = "0.2.0"


def custom_init(self):
    """
    init override
    """
    from os import chmod
    with open(f"{self.out_dir}/init_main.sh", 'w', encoding='utf-8') as main_init:
        main_init.write("#!/bin/bash\n")
        [main_init.write(f"{line}\n") for line in self.generate_init_main()]
    chmod(f"{self.out_dir}/init_main.sh", 0o755)
    return serial_init(self)


def serial_init(self):
    """
    start agetty
    """
    name = self.config_dict['primary_console']
    out_str = f"agetty --autologin root --login-program /init_main.sh {name}"

    config = self.config_dict['serial'][name]

    if config.get('local'):
        out_str += " -L"

    if config.get('baud'):
        out_str += f" {config['baud']}"

    if config.get('type'):
        out_str += f" {config['type']}"

    return [out_str]

